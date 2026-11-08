"""The evaluation question set: one JSON object per line."""

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from datasheet_assistant.normalise import normalise
from datasheet_assistant.numbers import Number, extract_numbers

ID_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
MAX_QUESTIONS = 1000

ANSWERABLE_FIELDS = frozenset(
    {"id", "question", "datasheet", "answerable", "pages", "numbers", "keywords"}
)
UNANSWERABLE_FIELDS = frozenset({"id", "question", "datasheet", "answerable"})


@dataclass(frozen=True, slots=True)
class Expected:
    """What a correct answer states, and the pages that state it."""

    pages: tuple[int, ...]
    """1-based page numbers, any of which holds the answer."""
    numbers: frozenset[Number]
    keywords: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Question:
    id: str
    text: str
    datasheet: str
    expected: Expected | None
    """None when the datasheet does not answer the question."""


def load_questions(path: Path, pages: Mapping[str, Sequence[str]]) -> list[Question]:
    """Parse the question file against the ingested `pages`.

    Each line is an object with "id", "question", "datasheet" and boolean
    "answerable". An answerable question also has "pages", "numbers" (each a
    string holding one number) and "keywords", with at least one number or
    keyword, and every number must appear on one of its pages. Raises
    ValueError naming the line and field of the first problem.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    questions = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            questions.append(_parse_question(json.loads(line), pages))
        except (json.JSONDecodeError, ValueError) as error:
            raise ValueError(f"{path} line {line_number}: {error}") from error
    if not questions:
        raise ValueError(f"{path}: expected at least one question")
    if len(questions) > MAX_QUESTIONS:
        raise ValueError(
            f"{path}: expected at most {MAX_QUESTIONS} questions, got {len(questions)}"
        )
    ids = [question.id for question in questions]
    duplicates = sorted({id_ for id_ in ids if ids.count(id_) > 1})
    if duplicates:
        raise ValueError(f"{path}: duplicate question ids {duplicates}")
    return questions


def _parse_question(entry: Any, pages: Mapping[str, Sequence[str]]) -> Question:
    if not isinstance(entry, dict):
        raise ValueError(f"expected an object, got {entry!r}")
    answerable = entry.get("answerable")
    if not isinstance(answerable, bool):
        raise ValueError(f"expected boolean 'answerable', got {answerable!r}")
    allowed = ANSWERABLE_FIELDS if answerable else UNANSWERABLE_FIELDS
    if entry.keys() != allowed:
        raise ValueError(
            f"expected fields {sorted(allowed)}, got {sorted(entry.keys())}"
        )
    id_ = _string(entry, "id")
    if not ID_PATTERN.fullmatch(id_):
        raise ValueError(f"expected an id like 'bme280-i2c-address', got {id_!r}")
    datasheet = _string(entry, "datasheet")
    datasheet_pages = pages.get(datasheet)
    if datasheet_pages is None:
        raise ValueError(
            f"unknown datasheet {datasheet!r}, expected one of {sorted(pages)}"
        )
    expected = _parse_expected(entry, datasheet_pages) if answerable else None
    return Question(id_, _string(entry, "question"), datasheet, expected)


def _parse_expected(entry: dict[str, Any], datasheet_pages: Sequence[str]) -> Expected:
    page_numbers = entry["pages"]
    if (
        not isinstance(page_numbers, list)
        or not page_numbers
        or not all(type(page) is int for page in page_numbers)
        or not all(1 <= page <= len(datasheet_pages) for page in page_numbers)
    ):
        raise ValueError(
            f"expected 'pages' to list pages from 1 to {len(datasheet_pages)}, "
            f"got {page_numbers!r}"
        )
    numbers = frozenset(_parse_number(text) for text in _strings(entry, "numbers"))
    keywords = tuple(_strings(entry, "keywords"))
    if not numbers and not keywords:
        raise ValueError("expected at least one entry in 'numbers' or 'keywords'")
    on_pages: set[Number] = set()
    for page in page_numbers:
        on_pages |= extract_numbers(datasheet_pages[page - 1])
    missing = numbers - on_pages
    if missing:
        listed = ", ".join(sorted(str(number) for number in missing))
        raise ValueError(f"numbers {listed} appear on none of pages {page_numbers}")
    return Expected(tuple(page_numbers), numbers, keywords)


def _parse_number(text: str) -> Number:
    found = extract_numbers(text)
    if len(found) != 1:
        raise ValueError(f"expected one number in {text!r}, got {len(found)}")
    return found.pop()


def _string(entry: dict[str, Any], key: str) -> str:
    value = entry[key]
    if not isinstance(value, str) or not normalise(value):
        raise ValueError(f"expected non-empty string '{key}', got {value!r}")
    return value


def _strings(entry: dict[str, Any], key: str) -> list[str]:
    values = entry[key]
    if not isinstance(values, list) or not all(
        isinstance(value, str) and normalise(value) for value in values
    ):
        raise ValueError(f"expected '{key}' to list non-empty strings, got {values!r}")
    return values
