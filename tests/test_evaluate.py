import csv
import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from datasheet_assistant.answer import AnswerError, Unanswerable
from datasheet_assistant.evaluate import (
    Arm,
    Outcome,
    Record,
    evaluate,
    summarise,
    summary_table,
    write_run,
)
from datasheet_assistant.questions import AcceptedAnswer, Expected, Question
from datasheet_assistant.retrieve import Chunk
from datasheet_assistant.score import Score
from datasheet_assistant.verify import Answer, Citation

QUOTE = "Connecting SDO to GND results in slave address 1110110 (0x76)"
PAGES = {"bme280": ["Operating range -40 to +85 °C", QUOTE]}
ADDRESS = Question(
    "bme280-i2c-address",
    "What is the slave address of the BME280 with SDO on GND?",
    "bme280",
    Expected((2,), (AcceptedAnswer(frozenset({"0x76"}), ()),)),
)
PRICE = Question("bme280-price", "What does the BME280 slave cost?", "bme280", None)

VERIFIABLE = Answer("The address is 0x76.", (Citation("bme280", 2, QUOTE),))
UNVERIFIABLE = Answer("The 7-bit address is 0x76.", (Citation("bme280", 2, QUOTE),))


class FakeAnswerer:
    """Replies by question text, and records every question it is asked."""

    def __init__(self, replies: dict[str, Answer | Unanswerable | AnswerError]) -> None:
        self.replies = replies
        self.asked: list[str] = []

    def reply(self, question: str) -> Answer | Unanswerable:
        self.asked.append(question)
        reply = self.replies[question]
        if isinstance(reply, AnswerError):
            raise reply
        return reply

    def from_excerpts(
        self, question: str, chunks: Sequence[Chunk]
    ) -> Answer | Unanswerable:
        return self.reply(question)


def by_arm(
    records: list[Record], question: Question, run: int = 1
) -> dict[Arm, Record]:
    return {
        record.arm: record
        for record in records
        if record.question == question and record.run == run
    }


def run(memory: FakeAnswerer, excerpts: FakeAnswerer, runs: int = 1) -> list[Record]:
    return evaluate([ADDRESS, PRICE], PAGES, memory.reply, excerpts.from_excerpts, runs)


def test_check_arm_derives_from_search_arm_without_a_model_call() -> None:
    memory = FakeAnswerer({ADDRESS.text: VERIFIABLE, PRICE.text: Unanswerable()})
    excerpts = FakeAnswerer({ADDRESS.text: UNVERIFIABLE, PRICE.text: Unanswerable()})

    records = run(memory, excerpts, runs=2)

    assert sorted(excerpts.asked) == sorted([ADDRESS.text, PRICE.text] * 2)
    arms = by_arm(records, ADDRESS, run=2)
    assert arms[Arm.MODEL_WITH_SEARCH].outcome == Outcome.ANSWERED
    assert arms[Arm.MODEL_WITH_SEARCH].score == Score.CORRECT
    checked = arms[Arm.SEARCH_WITH_CHECK]
    assert checked.outcome == Outcome.WITHHELD
    assert checked.answer == UNVERIFIABLE
    assert checked.score == Score.FALSE_REFUSAL
    assert checked.detail.startswith("number_not_in_quotes")


def test_verified_answer_is_shown_by_check_arm() -> None:
    memory = FakeAnswerer({ADDRESS.text: Unanswerable(), PRICE.text: Unanswerable()})
    excerpts = FakeAnswerer({ADDRESS.text: VERIFIABLE, PRICE.text: Unanswerable()})

    arms = by_arm(run(memory, excerpts), ADDRESS)

    assert arms[Arm.MODEL_ALONE].score == Score.FALSE_REFUSAL
    assert arms[Arm.SEARCH_WITH_CHECK].outcome == Outcome.ANSWERED
    assert arms[Arm.SEARCH_WITH_CHECK].score == Score.CORRECT
    assert arms[Arm.SEARCH_WITH_CHECK].cites_expected_page is True


def test_failed_request_is_an_error_not_a_refusal() -> None:
    failure = AnswerError("Claude API request failed: down")
    memory = FakeAnswerer({ADDRESS.text: failure, PRICE.text: Unanswerable()})
    excerpts = FakeAnswerer({ADDRESS.text: failure, PRICE.text: Unanswerable()})

    records = run(memory, excerpts)

    for record in by_arm(records, ADDRESS).values():
        assert record.outcome == Outcome.ERROR
        assert record.score is None
        assert record.category == "error"
        assert "request failed" in record.detail
    assert by_arm(records, PRICE)[Arm.MODEL_ALONE].score == Score.CORRECT_REFUSAL


def test_question_matching_no_excerpt_skips_the_search_arm_call() -> None:
    unmatched = Question("zzz", "zzz qqq", "bme280", None)
    memory = FakeAnswerer({unmatched.text: Unanswerable()})
    excerpts = FakeAnswerer({})

    records = evaluate([unmatched], PAGES, memory.reply, excerpts.from_excerpts, 1)

    assert excerpts.asked == []
    assert {record.score for record in records} == {Score.CORRECT_REFUSAL}


def test_records_are_ordered_by_run_question_and_arm() -> None:
    memory = FakeAnswerer({ADDRESS.text: VERIFIABLE, PRICE.text: Unanswerable()})

    records = run(memory, memory, runs=2)

    assert [(r.run, r.question.id, r.arm) for r in records] == [
        (run_number, question.id, arm)
        for run_number in (1, 2)
        for question in (ADDRESS, PRICE)
        for arm in Arm
    ]


@pytest.mark.parametrize("runs", [0, 6])
def test_rejects_run_count_out_of_range(runs: int) -> None:
    memory = FakeAnswerer({})

    with pytest.raises(ValueError, match="runs"):
        run(memory, memory, runs=runs)

    assert memory.asked == []


def test_summary_counts_each_category_per_run_and_shows_spread() -> None:
    memory = FakeAnswerer({ADDRESS.text: VERIFIABLE, PRICE.text: Unanswerable()})
    records = run(memory, memory, runs=2)
    flipped = [
        Record(
            r.run,
            r.question,
            r.arm,
            Outcome.UNANSWERABLE,
            None,
            "",
            Score.FALSE_REFUSAL,
            None,
        )
        if r.run == 2 and r.question == ADDRESS and r.arm == Arm.MODEL_ALONE
        else r
        for r in records
    ]

    counts = summarise(flipped)
    table = summary_table(counts)

    assert counts[Arm.MODEL_ALONE]["correct"] == [1, 0]
    assert counts[Arm.MODEL_ALONE]["false_refusal"] == [0, 1]
    assert counts[Arm.SEARCH_WITH_CHECK]["correct_refusal"] == [1, 1]
    assert "| A: model alone | 0.5 (0 to 1) | 0 | 1 | 0.5 (0 to 1) | 0 | 0 |" in table
    assert table.splitlines()[0] == (
        "| Arm | correct | wrong | correct refusal | false refusal | unplaced | error |"
    )


def test_writes_run_files_and_refuses_to_overwrite(tmp_path: Path) -> None:
    memory = FakeAnswerer({ADDRESS.text: UNVERIFIABLE, PRICE.text: Unanswerable()})
    records = run(memory, memory)
    directory = tmp_path / "run"

    write_run(records, "2 questions, 1 run.", directory)

    answers = [
        json.loads(line)
        for line in (directory / "answers.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    withheld = answers[2]
    assert withheld["arm"] == "search_with_check"
    assert withheld["outcome"] == "withheld"
    assert withheld["citations"][0]["page"] == 2
    with (directory / "scores.csv").open(encoding="utf-8", newline="") as file:
        scores = list(csv.DictReader(file))
    assert len(scores) == 6
    assert scores[0]["cites_expected_page"] == "True"
    assert scores[3]["cites_expected_page"] == ""
    summary = (directory / "summary.md").read_text(encoding="utf-8")
    assert "2 questions, 1 run." in summary
    assert "| C: search with check |" in summary
    assert (directory / "summary.csv").exists()
    with pytest.raises(FileExistsError):
        write_run(records, "again", directory)
