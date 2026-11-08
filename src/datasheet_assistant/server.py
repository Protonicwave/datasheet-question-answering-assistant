"""HTTP API behind the web page: answer a question, render a datasheet page."""

import logging
from collections.abc import Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal, assert_never

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, StringConstraints

from datasheet_assistant.answer import AnswerError, RejectedAttempt, Unanswerable
from datasheet_assistant.locate import Box
from datasheet_assistant.normalise import normalise_with_origins
from datasheet_assistant.numbers import Number, extract_numbers, number_spans
from datasheet_assistant.pdf_pages import PdfPages
from datasheet_assistant.pipeline import Answerer, Checked, ask
from datasheet_assistant.retrieve import Index
from datasheet_assistant.verify import Answer, Rejected, RejectionReason, Verified

logger = logging.getLogger(__name__)

# Datasheet questions are a sentence or two; a cap keeps one request from
# filling the prompt.
MAX_QUESTION_CHARACTERS = 500
# Browsers revalidate each page against an ETag tied to the PDF file, so a
# re-ingested datasheet is never shown from a stale image under new marks.
PAGE_CACHE_CONTROL = "no-cache"

Question = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=MAX_QUESTION_CHARACTERS
    ),
]


class AskRequest(BaseModel):
    question: Question


class NumberMarksBody(BaseModel):
    value: str
    boxes: list[Box]


class MarksBody(BaseModel):
    quote: list[Box]
    numbers: list[NumberMarksBody]


class CitationBody(BaseModel):
    datasheet: str
    page: int
    page_count: int | None
    """None if no datasheet has this name."""
    quote: str
    marks: MarksBody | None
    """None if the quote was not found on a page that exists."""


class SegmentBody(BaseModel):
    text: str
    number: str | None
    """The number's value, as in NumberMarksBody.value, if the segment is one."""


class RejectionBody(BaseModel):
    reason: RejectionReason
    detail: str


class DraftBody(BaseModel):
    segments: list[SegmentBody]
    citations: list[CitationBody]
    rejection: RejectionBody | None


class DatasheetBody(BaseModel):
    name: str
    page_count: int


class AskResponse(BaseModel):
    outcome: Literal["verified", "withheld", "unanswerable"]
    answer: DraftBody | None
    """The verified answer; None unless the outcome is verified."""
    drafts: list[DraftBody]
    """Answers the check rejected, oldest first. A withheld outcome ends
    with the last draft."""


def create_app(
    index: Index,
    pages: Mapping[str, Sequence[str]],
    answerer: Answerer,
    pdf_pages: PdfPages,
    web_dir: Path | None,
) -> FastAPI:
    """The API under /api and, if `web_dir` is given, the built web page.

    Meant for one person on this machine: concurrent questions are not
    limited beyond the server's thread pool, and each spends API credit.
    Locating quotes costs one PDF read per citation, bounded by the model's
    output limit and serialised by the pdfium lock.
    """
    app = FastAPI(title="Datasheet assistant")

    @app.post("/api/ask")
    def ask_question(request: AskRequest) -> AskResponse:
        try:
            checked = ask(request.question, index, pages, answerer)
        except AnswerError as error:
            logger.warning("answer failed: %s", error)
            raise HTTPException(status_code=502, detail=str(error)) from error
        return _ask_response(checked, pages, pdf_pages)

    @app.get("/api/datasheets")
    def list_datasheets() -> list[DatasheetBody]:
        return [
            DatasheetBody(name=name, page_count=len(texts))
            for name, texts in sorted(pages.items())
        ]

    @app.get("/api/pages/{datasheet}/{page}.png")
    def page_image(datasheet: str, page: int, request: Request) -> Response:
        page_count = len(pages.get(datasheet, ()))
        if not 1 <= page <= page_count:
            raise HTTPException(
                status_code=404, detail=f"no page {page} in datasheet {datasheet!r}"
            )
        headers = {
            "Cache-Control": PAGE_CACHE_CONTROL,
            "ETag": f'"{datasheet}-{page}-{pdf_pages.version(datasheet)}"',
        }
        if request.headers.get("If-None-Match") == headers["ETag"]:
            return Response(status_code=304, headers=headers)
        return Response(
            content=pdf_pages.render_png(datasheet, page),
            media_type="image/png",
            headers=headers,
        )

    if web_dir is not None:
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
    return app


def _ask_response(
    checked: Checked, pages: Mapping[str, Sequence[str]], pdf_pages: PdfPages
) -> AskResponse:
    drafts = [
        _draft_body(attempt.answer, attempt.rejection, pages, pdf_pages)
        for attempt in checked.revised
    ]
    match checked.final:
        case Verified(answer):
            return AskResponse(
                outcome="verified",
                answer=_draft_body(answer, None, pages, pdf_pages),
                drafts=drafts,
            )
        case RejectedAttempt() as attempt:
            drafts.append(
                _draft_body(attempt.answer, attempt.rejection, pages, pdf_pages)
            )
            return AskResponse(outcome="withheld", answer=None, drafts=drafts)
        case Unanswerable():
            return AskResponse(outcome="unanswerable", answer=None, drafts=drafts)
        case _:
            assert_never(checked.final)


def _draft_body(
    answer: Answer,
    rejection: Rejected | None,
    pages: Mapping[str, Sequence[str]],
    pdf_pages: PdfPages,
) -> DraftBody:
    numbers = extract_numbers(answer.text)
    citations = []
    for citation in answer.citations:
        datasheet_pages = pages.get(citation.datasheet)
        marks = None
        if datasheet_pages is not None and 1 <= citation.page <= len(datasheet_pages):
            found = pdf_pages.mark(
                citation.datasheet, citation.page, citation.quote, numbers
            )
            if found is not None:
                marks = MarksBody(
                    quote=list(found.quote),
                    numbers=[
                        NumberMarksBody(
                            value=_number_key(mark.value), boxes=list(mark.boxes)
                        )
                        for mark in found.numbers
                    ],
                )
        citations.append(
            CitationBody(
                datasheet=citation.datasheet,
                page=citation.page,
                page_count=None if datasheet_pages is None else len(datasheet_pages),
                quote=citation.quote,
                marks=marks,
            )
        )
    return DraftBody(
        segments=answer_segments(answer.text),
        citations=citations,
        rejection=None
        if rejection is None
        else RejectionBody(reason=rejection.reason, detail=rejection.detail),
    )


def answer_segments(text: str) -> list[SegmentBody]:
    """`text` split into plain runs and numbers, in order, so the page can
    link each number in the answer to the same value on the datasheet page.

    Numbers are read from the normalised text, as the check reads them, so
    a Unicode minus gives the same key as the page marks.
    """
    normalised, origins = normalise_with_origins(text)
    segments = []
    position = 0
    for span in number_spans(normalised):
        start, end = origins[span.start], origins[span.end - 1] + 1
        if start > position:
            segments.append(SegmentBody(text=text[position:start], number=None))
        segments.append(
            SegmentBody(text=text[start:end], number=_number_key(span.value))
        )
        position = end
    if position < len(text):
        segments.append(SegmentBody(text=text[position:], number=None))
    return segments


def _number_key(value: Number) -> str:
    """One spelling per value, so 0.10 in the answer meets 0.1 on the page."""
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    return value
