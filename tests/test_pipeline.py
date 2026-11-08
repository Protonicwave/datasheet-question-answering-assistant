from collections.abc import Sequence

from datasheet_assistant.answer import Unanswerable
from datasheet_assistant.pipeline import ask
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


class FakeAnswerer:
    def __init__(self, reply: Answer | Unanswerable) -> None:
        self.reply = reply
        self.excerpts: list[Chunk] = []

    def __call__(self, question: str, chunks: Sequence[Chunk]) -> Answer | Unanswerable:
        self.excerpts.extend(chunks)
        return self.reply


def test_verified_answer_reaches_the_user() -> None:
    reply = Answer("The address is 0x76.", (Citation("bme280", 2, QUOTE),))

    outcome = ask(QUESTION, INDEX, PAGES, FakeAnswerer(reply))

    assert outcome == Verified(reply)


def test_answerer_sees_retrieved_excerpts() -> None:
    answerer = FakeAnswerer(Unanswerable())

    ask(QUESTION, INDEX, PAGES, answerer)

    assert Chunk("bme280", 2, QUOTE) in answerer.excerpts


def test_answer_failing_the_check_is_rejected() -> None:
    reply = Answer("The address is 0x77.", (Citation("bme280", 2, QUOTE),))

    outcome = ask(QUESTION, INDEX, PAGES, FakeAnswerer(reply))

    assert isinstance(outcome, Rejected)
    assert outcome.reason == RejectionReason.NUMBER_NOT_IN_QUOTES


def test_unanswerable_passes_through() -> None:
    outcome = ask(QUESTION, INDEX, PAGES, FakeAnswerer(Unanswerable()))

    assert outcome == Unanswerable()


def test_question_matching_no_excerpt_is_unanswerable_without_asking() -> None:
    answerer = FakeAnswerer(Answer("unused", ()))

    outcome = ask("zzz qqq", INDEX, PAGES, answerer)

    assert outcome == Unanswerable()
    assert answerer.excerpts == []
