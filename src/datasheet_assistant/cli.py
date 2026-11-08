"""Command-line entry point."""

import argparse
import functools
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import assert_never

from datasheet_assistant.answer import (
    AnswerError,
    Unanswerable,
    answer_question,
    connect,
)
from datasheet_assistant.ingest import ingest, load_pages, load_sources
from datasheet_assistant.pipeline import ask
from datasheet_assistant.retrieve import Index, chunk_pages
from datasheet_assistant.verify import Rejected, Verified

SOURCES_PATH = Path("datasheets/sources.toml")
PDF_DIR = Path("data/pdfs")
PAGES_DIR = Path("data/pages")
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
    arguments = parser.parse_args(argv)

    try:
        if arguments.command == "ingest":
            output = _ingest()
        else:
            output = _ask(arguments.question)
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
    api_key = os.environ.get(API_KEY_VARIABLE)
    if not api_key:
        raise ValueError(f"{API_KEY_VARIABLE} is not set")
    pages = load_pages(PAGES_DIR)
    answerer = functools.partial(answer_question, connect(api_key))
    return render(ask(question, Index(chunk_pages(pages)), pages, answerer))


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
