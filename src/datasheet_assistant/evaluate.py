"""Runs the three evaluation arms over the question set and writes the results.

A: the model alone, answering from memory. B: the model answering from
retrieved excerpts. C: B's answers passed through the check. C makes no model
call of its own, so the check is the only difference between B and C.
"""

import csv
import json
import logging
import statistics
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import assert_never

from datasheet_assistant.answer import AnswerError, Unanswerable
from datasheet_assistant.pipeline import Answerer, answer_from_excerpts
from datasheet_assistant.questions import Question
from datasheet_assistant.retrieve import Index, chunk_pages
from datasheet_assistant.score import Score, cites_expected_page, score
from datasheet_assistant.verify import Answer, Rejected, verify

# Each worker makes one request at a time; the SDK retries rate limits.
MAX_CONCURRENT_REQUESTS = 4
MAX_RUNS = 5

ERROR = "error"
CATEGORIES = (*Score, ERROR)

logger = logging.getLogger(__name__)

type MemoryAnswerer = Callable[[str], Answer | Unanswerable]
type Reply = Answer | Unanswerable | AnswerError


class Arm(StrEnum):
    MODEL_ALONE = "model_alone"
    MODEL_WITH_SEARCH = "model_with_search"
    SEARCH_WITH_CHECK = "search_with_check"


ARM_LABELS = {
    Arm.MODEL_ALONE: "A: model alone",
    Arm.MODEL_WITH_SEARCH: "B: model with search",
    Arm.SEARCH_WITH_CHECK: "C: search with check",
}


class Outcome(StrEnum):
    ANSWERED = "answered"
    UNANSWERABLE = "unanswerable"
    WITHHELD = "withheld"
    """The model answered but the check rejected it, so the user is told the
    datasheet does not say."""
    ERROR = ERROR


@dataclass(frozen=True, slots=True)
class Record:
    run: int
    question: Question
    arm: Arm
    outcome: Outcome
    answer: Answer | None
    """The model's answer, whether shown or withheld."""
    detail: str
    """The error, or why the answer was withheld; empty otherwise."""
    score: Score | None
    """None when the request failed."""
    cites_expected_page: bool | None

    @property
    def category(self) -> str:
        return ERROR if self.score is None else self.score


def evaluate(
    questions: Sequence[Question],
    pages: Mapping[str, Sequence[str]],
    from_memory: MemoryAnswerer,
    from_excerpts: Answerer,
    runs: int,
) -> list[Record]:
    """Run every question through all three arms `runs` times, searching and
    checking against `pages`.

    A failed request is recorded as an error, never as a refusal. Records
    come back ordered by run, then question, then arm.
    """
    if not 1 <= runs <= MAX_RUNS:
        raise ValueError(f"expected 1 to {MAX_RUNS} runs, got {runs}")
    index = Index(chunk_pages(pages))
    tasks = [(run, question) for run in range(1, runs + 1) for question in questions]

    def run_task(task: tuple[int, Question]) -> list[Record]:
        run, question = task
        memory_reply = _reply(lambda: from_memory(question.text))
        excerpt_reply = _reply(
            lambda: answer_from_excerpts(question.text, index, from_excerpts)
        )
        logger.info("run %d: %s done", run, question.id)
        return [
            _record(run, question, Arm.MODEL_ALONE, memory_reply),
            _record(run, question, Arm.MODEL_WITH_SEARCH, excerpt_reply),
            _checked_record(run, question, excerpt_reply, pages),
        ]

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_REQUESTS) as pool:
        return [record for records in pool.map(run_task, tasks) for record in records]


def _reply(call: Callable[[], Answer | Unanswerable]) -> Reply:
    try:
        return call()
    except AnswerError as error:
        return error


def _record(run: int, question: Question, arm: Arm, reply: Reply) -> Record:
    match reply:
        case AnswerError():
            return Record(
                run, question, arm, Outcome.ERROR, None, str(reply), None, None
            )
        case Unanswerable():
            return Record(
                run,
                question,
                arm,
                Outcome.UNANSWERABLE,
                None,
                "",
                score(question, None),
                None,
            )
        case Answer():
            return Record(
                run,
                question,
                arm,
                Outcome.ANSWERED,
                reply,
                "",
                score(question, reply.text),
                cites_expected_page(question, reply),
            )
        case _:
            assert_never(reply)


def _checked_record(
    run: int, question: Question, reply: Reply, pages: Mapping[str, Sequence[str]]
) -> Record:
    if isinstance(reply, Answer):
        verdict = verify(reply, pages)
        if isinstance(verdict, Rejected):
            return Record(
                run,
                question,
                Arm.SEARCH_WITH_CHECK,
                Outcome.WITHHELD,
                reply,
                f"{verdict.reason}: {verdict.detail}",
                score(question, None),
                cites_expected_page(question, reply),
            )
    return _record(run, question, Arm.SEARCH_WITH_CHECK, reply)


def summarise(records: Sequence[Record]) -> dict[Arm, dict[str, list[int]]]:
    """Count each category per arm, with one count per run in run order."""
    runs = max((record.run for record in records), default=0)
    counts = {arm: {category: [0] * runs for category in CATEGORIES} for arm in Arm}
    for record in records:
        counts[record.arm][record.category][record.run - 1] += 1
    return counts


def summary_table(counts: Mapping[Arm, Mapping[str, Sequence[int]]]) -> str:
    """A Markdown table of `summarise` output: the count when every run agrees,
    otherwise the mean with the range across runs."""
    header = ["Arm", *(category.replace("_", " ") for category in CATEGORIES)]
    rows = [
        [ARM_LABELS[arm], *(_cell(counts[arm][category]) for category in CATEGORIES)]
        for arm in Arm
    ]
    lines = [header, ["---"] * len(header), *rows]
    return "\n".join("| " + " | ".join(line) + " |" for line in lines)


def _cell(per_run: Sequence[int]) -> str:
    if min(per_run) == max(per_run):
        return str(per_run[0])
    return f"{statistics.fmean(per_run):.1f} ({min(per_run)} to {max(per_run)})"


def write_run(records: Sequence[Record], heading: str, directory: Path) -> None:
    """Write answers, per-question scores and the summary into a new `directory`.

    Raises FileExistsError rather than overwrite an earlier run.
    """
    directory.mkdir(parents=True, exist_ok=False)
    with (directory / "answers.jsonl").open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(_answer_row(record), ensure_ascii=False) + "\n")
    with (directory / "scores.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(
            ["run", "question", "arm", "outcome", "score", "cites_expected_page"]
        )
        for record in records:
            writer.writerow(
                [
                    record.run,
                    record.question.id,
                    record.arm,
                    record.outcome,
                    record.category,
                    ""
                    if record.cites_expected_page is None
                    else record.cites_expected_page,
                ]
            )
    counts = summarise(records)
    with (directory / "summary.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["arm", "category", "run", "count"])
        for arm, by_category in counts.items():
            for category, per_run in by_category.items():
                for run, count in enumerate(per_run, start=1):
                    writer.writerow([arm, category, run, count])
    (directory / "summary.md").write_text(
        f"# Evaluation summary\n\n{heading}\n\n{summary_table(counts)}\n",
        encoding="utf-8",
    )


def _answer_row(record: Record) -> dict[str, object]:
    answer = record.answer
    return {
        "run": record.run,
        "question": record.question.id,
        "arm": record.arm,
        "outcome": record.outcome,
        "score": record.category,
        "cites_expected_page": record.cites_expected_page,
        "answer": None if answer is None else answer.text,
        "citations": []
        if answer is None
        else [
            {"datasheet": c.datasheet, "page": c.page, "quote": c.quote}
            for c in answer.citations
        ],
        "detail": record.detail,
    }
