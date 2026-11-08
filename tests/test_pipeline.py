from collections.abc import Sequence

import pytest

from datasheet_assistant.answer import AnswerError, RejectedAttempt, Unanswerable
from datasheet_assistant.pipeline import (
    MAX_REVISIONS,
    Checked,
    ask,
    check_with_retry,
)
from datasheet_assistant.retrieve import Chunk, Index, chunk_pages
from datasheet_assistant.verify import (
    Answer,
    Citation,
    Rejected,
    RejectionReason,
    Verified,
)

PAGES = {
    "bme280": [
        "Operating range T Operational -40 25 85 °C",
        "Connecting SDO to GND results in slave address 1110110 (0x76)",
    ]
}
INDEX = Index(chunk_pages(PAGES))
QUESTION = "What is the I2C slave address of the BME280 when SDO is on GND?"
QUOTE = "Connecting SDO to GND results in slave address 1110110 (0x76)"


VERIFIABLE = Answer("The address is 0x76.", (Citation("bme280", 2, QUOTE),))
UNVERIFIABLE = Answer("The address is 0x77.", (Citation("bme280", 2, QUOTE),))


class FakeAnswerer:
    """Gives its replies in order, repeating the last, and records what it
    was sent."""

    def __init__(self, *replies: Answer | Unanswerable | AnswerError) -> None:
        self.replies = list(replies)
        self.excerpts: list[Chunk] = []
        self.histories: list[tuple[RejectedAttempt, ...]] = []

    def __call__(
        self,
        question: str,
        chunks: Sequence[Chunk],
        rejected: Sequence[RejectedAttempt],
    ) -> Answer | Unanswerable:
        self.excerpts.extend(chunks)
        self.histories.append(tuple(rejected))
        reply = self.replies[min(len(self.histories), len(self.replies)) - 1]
        if isinstance(reply, AnswerError):
            raise reply
        return reply


def test_verified_answer_reaches_the_user() -> None:
    outcome = ask(QUESTION, INDEX, PAGES, FakeAnswerer(VERIFIABLE))

    assert outcome == Verified(VERIFIABLE)


def test_answerer_sees_retrieved_excerpts() -> None:
    answerer = FakeAnswerer(Unanswerable())

    ask(QUESTION, INDEX, PAGES, answerer)

    assert Chunk("bme280", 2, QUOTE) in answerer.excerpts


def test_answer_failing_every_revision_is_rejected() -> None:
    answerer = FakeAnswerer(UNVERIFIABLE)

    outcome = ask(QUESTION, INDEX, PAGES, answerer)

    assert isinstance(outcome, Rejected)
    assert outcome.reason == RejectionReason.NUMBER_NOT_IN_QUOTES
    assert len(answerer.histories) == 1 + MAX_REVISIONS


def test_ask_shows_an_answer_verified_on_revision() -> None:
    outcome = ask(QUESTION, INDEX, PAGES, FakeAnswerer(UNVERIFIABLE, VERIFIABLE))

    assert outcome == Verified(VERIFIABLE)


def test_unanswerable_passes_through() -> None:
    outcome = ask(QUESTION, INDEX, PAGES, FakeAnswerer(Unanswerable()))

    assert outcome == Unanswerable()


def test_question_matching_no_excerpt_is_unanswerable_without_asking() -> None:
    answerer = FakeAnswerer(Answer("unused", ()))

    outcome = ask("zzz qqq", INDEX, PAGES, answerer)

    assert outcome == Unanswerable()
    assert answerer.excerpts == []


def test_verified_first_answer_needs_no_revision() -> None:
    answerer = FakeAnswerer()

    checked = check_with_retry(QUESTION, (), VERIFIABLE, PAGES, answerer)

    assert checked == Checked(Verified(VERIFIABLE), ())
    assert answerer.histories == []


def test_rejected_answer_is_sent_back_with_the_rejection() -> None:
    chunks = INDEX.search(QUESTION, 2)
    answerer = FakeAnswerer(VERIFIABLE)

    checked = check_with_retry(QUESTION, chunks, UNVERIFIABLE, PAGES, answerer)

    assert checked.final == Verified(VERIFIABLE)
    [attempt] = checked.revised
    assert attempt.answer == UNVERIFIABLE
    assert attempt.rejection.reason == RejectionReason.NUMBER_NOT_IN_QUOTES
    assert answerer.histories == [(attempt,)]
    assert answerer.excerpts == list(chunks)


def test_revisions_stop_at_the_bound_with_every_attempt_kept() -> None:
    answerer = FakeAnswerer(UNVERIFIABLE)

    checked = check_with_retry(QUESTION, (), UNVERIFIABLE, PAGES, answerer)

    assert isinstance(checked.final, RejectedAttempt)
    assert checked.final.answer == UNVERIFIABLE
    assert len(checked.revised) == MAX_REVISIONS
    assert [len(history) for history in answerer.histories] == list(
        range(1, MAX_REVISIONS + 1)
    )


def test_revision_marked_unanswerable_is_a_refusal() -> None:
    checked = check_with_retry(
        QUESTION, (), UNVERIFIABLE, PAGES, FakeAnswerer(Unanswerable())
    )

    assert checked.final == Unanswerable()
    assert len(checked.revised) == 1


def test_failed_revision_request_raises() -> None:
    answerer = FakeAnswerer(AnswerError("Claude API request failed: down"))

    with pytest.raises(AnswerError, match="request failed"):
        check_with_retry(QUESTION, (), UNVERIFIABLE, PAGES, answerer)
