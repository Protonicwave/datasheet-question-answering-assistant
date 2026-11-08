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

import uvicorn

from datasheet_assistant.answer import (
    MODEL,
    AnswerError,
    RejectedAttempt,
    Unanswerable,
    answer_from_memory,
    answer_question,
    connect,
)
from datasheet_assistant.evaluate import evaluate, summarise, summary_table, write_run
from datasheet_assistant.ingest import ingest, load_pages, load_sources
from datasheet_assistant.pdf_pages import PdfPages
from datasheet_assistant.pipeline import MAX_REVISIONS, ask
from datasheet_assistant.questions import load_questions
from datasheet_assistant.retrieve import Index, chunk_pages
from datasheet_assistant.server import create_app
from datasheet_assistant.verify import Verified

SOURCES_PATH = Path("datasheets/sources.toml")
PDF_DIR = Path("data/pdfs")
PAGES_DIR = Path("data/pages")
RUNS_DIR = Path("eval/runs")
DEFAULT_RUNS = 3
API_KEY_VARIABLE = "ANTHROPIC_API_KEY"
WEB_DIR = Path("web/dist")
# Loopback only: the server spends the API key of whoever runs it and has
# no accounts, so it is not for a shared network.
SERVE_HOST = "127.0.0.1"
DEFAULT_PORT = 8000

NOT_IN_DATASHEET = "The datasheet does not say."
# An answer that failed the check may still be true, so a withheld answer
# must not be reported as the datasheet being silent.
NO_VERIFIED_ANSWER = "No verified answer."


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
        help="run a question set through the model alone, the model with "
        "search, search with the check, and search with the check and retry",
    )
    evaluate_parser.add_argument(
        "--questions",
        type=Path,
        required=True,
        help="question file, such as eval/development.jsonl",
    )
    evaluate_parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    serve_parser = commands.add_parser(
        "serve", help="serve the web page and its API on this machine"
    )
    serve_parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    arguments = parser.parse_args(argv)

    try:
        if arguments.command == "ingest":
            output = _ingest()
        elif arguments.command == "ask":
            output = _ask(arguments.question)
        elif arguments.command == "serve":
            output = _serve(arguments.port)
        else:
            output = _evaluate(arguments.questions, arguments.runs)
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
    return render(ask(question, Index(chunk_pages(pages)), pages, answerer).final)


def _serve(port: int) -> str:
    client = connect(_api_key())
    pages = load_pages(PAGES_DIR)
    missing = [name for name in pages if not (PDF_DIR / f"{name}.pdf").is_file()]
    if missing:
        raise ValueError(
            f"{PDF_DIR}: no PDF for {', '.join(missing)}; run the ingest command"
        )
    web_dir = WEB_DIR if WEB_DIR.is_dir() else None
    if web_dir is None:
        print(f"{WEB_DIR} not found: serving the API only", file=sys.stderr)
    app = create_app(
        Index(chunk_pages(pages)),
        pages,
        functools.partial(answer_question, client),
        PdfPages(PDF_DIR),
        web_dir,
    )
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    uvicorn.run(app, host=SERVE_HOST, port=port)
    return "server stopped"


def _evaluate(questions_path: Path, runs: int) -> str:
    client = connect(_api_key())
    pages = load_pages(PAGES_DIR)
    questions = load_questions(questions_path, pages)
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
        f"{questions_path.as_posix()}: {len(questions)} questions "
        f"({answerable} answerable), "
        f"{runs} runs, model {MODEL}, "
        f"revisions per rejected answer: at most {MAX_REVISIONS}."
    )
    write_run(records, heading, directory)
    return f"wrote {directory}\n\n{summary_table(summarise(records))}"


def _api_key() -> str:
    api_key = os.environ.get(API_KEY_VARIABLE)
    if not api_key:
        raise ValueError(f"{API_KEY_VARIABLE} is not set")
    return api_key


def render(outcome: Verified | RejectedAttempt | Unanswerable) -> str:
    """Format an outcome for the terminal. Only a verified answer is shown."""
    match outcome:
        case Verified(answer):
            sources = "\n".join(
                f'{citation.datasheet}, page {citation.page}: "{citation.quote}"'
                for citation in answer.citations
            )
            return f"{answer.text}\n\n{sources}"
        case RejectedAttempt():
            return (
                f"{NO_VERIFIED_ANSWER}\n"
                f"(An answer was withheld: {outcome.rejection.detail}.)"
            )
        case Unanswerable():
            return NOT_IN_DATASHEET
        case _:
            assert_never(outcome)


if __name__ == "__main__":
    sys.exit(main())
