from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from datasheet_assistant.answer import AnswerError, RejectedAttempt, Unanswerable
from datasheet_assistant.ingest import extract_pages
from datasheet_assistant.pdf_pages import PdfPages
from datasheet_assistant.retrieve import Chunk, Index, chunk_pages
from datasheet_assistant.server import (
    MAX_QUESTION_CHARACTERS,
    answer_segments,
    create_app,
)
from datasheet_assistant.verify import Answer, Citation
from tests.pdf_builder import build_pdf

QUOTE = "Sleep current IDDSL 0.10 0.3 uA"
QUESTION = "What is the sleep current IDDSL of the part?"
VERIFIABLE = Answer("The sleep current is 0.1 uA.", (Citation("part", 2, QUOTE),))
UNVERIFIABLE = Answer("The sleep current is 0.2 uA.", (Citation("part", 2, QUOTE),))


class Replies:
    """An answerer giving its replies in order, repeating the last."""

    def __init__(self, *replies: Answer | Unanswerable | AnswerError) -> None:
        self.replies = list(replies)
        self.calls = 0

    def __call__(
        self,
        question: str,
        chunks: Sequence[Chunk],
        rejected: Sequence[RejectedAttempt],
    ) -> Answer | Unanswerable:
        reply = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        if isinstance(reply, AnswerError):
            raise reply
        return reply


@pytest.fixture
def pdf_dir(tmp_path: Path) -> Path:
    (tmp_path / "part.pdf").write_bytes(build_pdf(["Cover page", QUOTE]))
    return tmp_path


def client_for(pdf_dir: Path, answerer: Replies) -> TestClient:
    pages = {"part": extract_pages((pdf_dir / "part.pdf").read_bytes(), "part")}
    app = create_app(
        Index(chunk_pages(pages)), pages, answerer, PdfPages(pdf_dir), web_dir=None
    )
    return TestClient(app)


def ask(pdf_dir: Path, *replies: Answer | Unanswerable | AnswerError) -> Any:
    response = client_for(pdf_dir, Replies(*replies)).post(
        "/api/ask", json={"question": QUESTION}
    )
    assert response.status_code == 200
    return response.json()


def test_verified_answer_carries_its_citation_and_marks(pdf_dir: Path) -> None:
    body = ask(pdf_dir, VERIFIABLE)

    assert body["outcome"] == "verified"
    assert body["drafts"] == []
    (citation,) = body["answer"]["citations"]
    assert citation["datasheet"] == "part"
    assert (citation["page"], citation["page_count"]) == (2, 2)
    assert len(citation["marks"]["quote"]) == 1
    (number,) = citation["marks"]["numbers"]
    assert number["value"] == "0.1"
    assert set(number["boxes"][0]) == {"left", "top", "right", "bottom"}


def test_answer_numbers_are_segments_keyed_like_the_marks(pdf_dir: Path) -> None:
    body = ask(pdf_dir, VERIFIABLE)

    assert body["answer"]["segments"] == [
        {"text": "The sleep current is ", "number": None},
        {"text": "0.1", "number": "0.1"},
        {"text": " uA.", "number": None},
    ]


def test_answer_verified_on_revision_keeps_the_rejected_draft(pdf_dir: Path) -> None:
    body = ask(pdf_dir, UNVERIFIABLE, VERIFIABLE)

    assert body["outcome"] == "verified"
    (draft,) = body["drafts"]
    assert draft["rejection"]["reason"] == "number_not_in_quotes"
    assert draft["segments"][1] == {"text": "0.2", "number": "0.2"}


def test_answer_failing_every_check_is_withheld(pdf_dir: Path) -> None:
    body = ask(pdf_dir, UNVERIFIABLE)

    assert body["outcome"] == "withheld"
    assert body["answer"] is None
    assert len(body["drafts"]) == 2
    assert all(draft["rejection"] is not None for draft in body["drafts"])
    assert body["drafts"][-1]["citations"][0]["marks"]["quote"]


def test_unanswerable_question(pdf_dir: Path) -> None:
    body = ask(pdf_dir, Unanswerable())

    assert body == {"outcome": "unanswerable", "answer": None, "drafts": []}


def test_draft_citing_a_missing_page_has_no_marks(pdf_dir: Path) -> None:
    beyond = Answer("It is 0.1 uA.", (Citation("part", 9, QUOTE),))

    body = ask(pdf_dir, beyond)

    citation = body["drafts"][-1]["citations"][0]
    assert (citation["page_count"], citation["marks"]) == (2, None)


def test_draft_citing_an_unknown_datasheet_has_no_page_count(pdf_dir: Path) -> None:
    unknown = Answer("It is 0.1 uA.", (Citation("other", 2, QUOTE),))

    body = ask(pdf_dir, unknown)

    citation = body["drafts"][-1]["citations"][0]
    assert (citation["page_count"], citation["marks"]) == (None, None)


def test_failed_model_request_is_a_bad_gateway(pdf_dir: Path) -> None:
    client = client_for(pdf_dir, Replies(AnswerError("Claude API request failed")))

    response = client.post("/api/ask", json={"question": QUESTION})

    assert response.status_code == 502
    assert "request failed" in response.json()["detail"]


@pytest.mark.parametrize(
    "question",
    ["", "   ", "x" * (MAX_QUESTION_CHARACTERS + 1)],
    ids=["empty", "blank", "too-long"],
)
def test_rejects_a_question_outside_the_limits(pdf_dir: Path, question: str) -> None:
    answerer = Replies(VERIFIABLE)

    response = client_for(pdf_dir, answerer).post(
        "/api/ask", json={"question": question}
    )

    assert response.status_code == 422
    assert answerer.calls == 0


def test_serves_a_page_as_a_png_to_revalidate(pdf_dir: Path) -> None:
    response = client_for(pdf_dir, Replies()).get("/api/pages/part/2.png")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "no-cache"
    assert response.content.startswith(b"\x89PNG")


@pytest.mark.parametrize(
    "path",
    ["/api/pages/part/0.png", "/api/pages/part/3.png", "/api/pages/other/1.png"],
    ids=["page-zero", "past-the-end", "unknown-datasheet"],
)
def test_page_outside_the_datasheets_is_not_found(pdf_dir: Path, path: str) -> None:
    response = client_for(pdf_dir, Replies()).get(path)

    assert response.status_code == 404


def test_lists_each_datasheet_with_its_page_count(pdf_dir: Path) -> None:
    response = client_for(pdf_dir, Replies()).get("/api/datasheets")

    assert response.json() == [{"name": "part", "page_count": 2}]


def test_a_unicode_minus_in_the_answer_keys_like_the_page_marks() -> None:
    text = "The range is \N{MINUS SIGN}40 to 85 \N{DEGREE SIGN}C."

    segments = answer_segments(text)

    assert [segment.number for segment in segments if segment.number] == ["-40", "85"]
    assert "".join(segment.text for segment in segments) == text


def test_unchanged_page_is_not_sent_again(pdf_dir: Path) -> None:
    client = client_for(pdf_dir, Replies())
    tag = client.get("/api/pages/part/2.png").headers["etag"]

    response = client.get("/api/pages/part/2.png", headers={"If-None-Match": tag})

    assert response.status_code == 304
    assert response.content == b""


def test_replaced_pdf_gets_a_new_tag(pdf_dir: Path) -> None:
    client = client_for(pdf_dir, Replies())
    before = client.get("/api/pages/part/2.png").headers["etag"]
    (pdf_dir / "part.pdf").write_bytes(build_pdf(["Cover page", QUOTE, "Extra"]))

    after = client.get("/api/pages/part/2.png").headers["etag"]

    assert before != after


def test_the_web_page_limits_questions_like_the_api() -> None:
    client_code = Path(__file__).parents[1].joinpath("web/src/api.ts")

    assert (
        f"MAX_QUESTION_CHARACTERS = {MAX_QUESTION_CHARACTERS};"
        in client_code.read_text(encoding="utf-8")
    )
