"""Command-line entry point."""

import argparse
import functools
import logging
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import assert_never

from datasheet_assistant.answer import (
    MODEL,
    AnswerError,
    Unanswerable,
    answer_from_memory,
    answer_question,
    connect,
)
from datasheet_assistant.evaluate import evaluate, summarise, summary_table, write_run
from datasheet_assistant.ingest import ingest, load_pages, load_sources
from datasheet_assistant.pipeline import ask
from datasheet_assistant.questions import load_questions
from datasheet_assistant.retrieve import Index, chunk_pages
from datasheet_assistant.verify import Rejected, Verified

SOURCES_PATH = Path("datasheets/sources.toml")
PDF_DIR = Path("data/pdfs")
PAGES_DIR = Path("data/pages")
QUESTIONS_PATH = Path("eval/questions.jsonl")
RUNS_DIR = Path("eval/runs")
DEFAULT_RUNS = 3
API_KEY_VARIABLE = "ANTHROPIC_API_KEY"

NOT_IN_DATASHEET = "The datasheet does not say."


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="datasheet-assistant")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "ingest", help="download the datasheets and extract their page text"
    )
    ask_parser = commands.add_parser(
        "ask", help="answer a question, citing the datasheet page and passage"
    )
    ask_parser.add_argument("question")
    evaluate_parser = commands.add_parser(
        "evaluate",
        help="run the question set through the model alone, the model with "
        "search, and search with the check",
    )
    evaluate_parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    arguments = parser.parse_args(argv)

    try:
        if arguments.command == "ingest":
            output = _ingest()
        elif arguments.command == "ask":
            output = _ask(arguments.question)
        else:
            output = _evaluate(arguments.runs)
    except (ValueError, OSError, AnswerError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(output)
    return 0


def _ingest() -> str:
    sources = load_sources(SOURCES_PATH)
    ingest(sources, PDF_DIR, PAGES_DIR)
    return f"ingested {len(sources)} datasheets into {PAGES_DIR}"


def _ask(question: str) -> str:
    if not question.strip():
        raise ValueError("expected a question, got an empty string")
    client = connect(_api_key())
    pages = load_pages(PAGES_DIR)
    answerer = functools.partial(answer_question, client)
    return render(ask(question, Index(chunk_pages(pages)), pages, answerer))


def _evaluate(runs: int) -> str:
    client = connect(_api_key())
    pages = load_pages(PAGES_DIR)
    questions = load_questions(QUESTIONS_PATH, pages)
    directory = RUNS_DIR / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    records = evaluate(
        questions,
        pages,
        functools.partial(answer_from_memory, client),
        functools.partial(answer_question, client),
        runs,
    )
    answerable = sum(question.expected is not None for question in questions)
    heading = (
        f"{len(questions)} questions ({answerable} answerable), "
        f"{runs} runs, model {MODEL}."
    )
    write_run(records, heading, directory)
    return f"wrote {directory}\n\n{summary_table(summarise(records))}"


def _api_key() -> str:
    api_key = os.environ.get(API_KEY_VARIABLE)
    if not api_key:
        raise ValueError(f"{API_KEY_VARIABLE} is not set")
    return api_key


def render(outcome: Verified | Rejected | Unanswerable) -> str:
    """Format an outcome for the terminal. Only a verified answer is shown."""
    match outcome:
        case Verified(answer):
            sources = "\n".join(
                f'{citation.datasheet}, page {citation.page}: "{citation.quote}"'
                for citation in answer.citations
            )
            return f"{answer.text}\n\n{sources}"
        case Rejected(_, detail):
            return f"{NOT_IN_DATASHEET}\n(An answer was withheld: {detail}.)"
        case Unanswerable():
            return NOT_IN_DATASHEET
        case _:
            assert_never(outcome)


if __name__ == "__main__":
    sys.exit(main())
