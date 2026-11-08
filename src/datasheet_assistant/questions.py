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
OPTIONAL_ANSWERABLE_FIELDS = frozenset({"alternatives"})
UNANSWERABLE_FIELDS = frozenset({"id", "question", "datasheet", "answerable"})
ALTERNATIVE_FIELDS = frozenset({"numbers", "keywords"})
MAX_ALTERNATIVES = 5


@dataclass(frozen=True, slots=True)
class AcceptedAnswer:
    """Numbers and keywords that together make a correct answer."""

    numbers: frozenset[Number]
    keywords: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Expected:
    """What a correct answer states, and the pages that state it."""

    pages: tuple[int, ...]
    """1-based page numbers, any of which holds the answer."""
    accepted: tuple[AcceptedAnswer, ...]
    """The answer as the datasheet states it, then any equivalent forms, such
    as the same value in another unit."""


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
    keyword, and every number must appear on one of its pages. It may add
    "alternatives": a list of objects with "numbers" and "keywords" giving
    equivalent answers, which need not appear on the page. Raises
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
    required = ANSWERABLE_FIELDS if answerable else UNANSWERABLE_FIELDS
    optional = OPTIONAL_ANSWERABLE_FIELDS if answerable else frozenset()
    if not required <= entry.keys() <= required | optional:
        raise ValueError(
            f"expected fields {sorted(required)}, optionally {sorted(optional)}, "
            f"got {sorted(entry.keys())}"
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
    stated = _parse_accepted(entry)
    on_pages: set[Number] = set()
    for page in page_numbers:
        on_pages |= extract_numbers(datasheet_pages[page - 1])
    missing = stated.numbers - on_pages
    if missing:
        listed = ", ".join(sorted(str(number) for number in missing))
        raise ValueError(f"numbers {listed} appear on none of pages {page_numbers}")
    alternatives = _parse_alternatives(entry) if "alternatives" in entry else []
    return Expected(tuple(page_numbers), (stated, *alternatives))


def _parse_alternatives(entry: dict[str, Any]) -> list[AcceptedAnswer]:
    alternatives = entry["alternatives"]
    if (
        not isinstance(alternatives, list)
        or not 1 <= len(alternatives) <= MAX_ALTERNATIVES
    ):
        raise ValueError(
            f"expected 'alternatives' to list 1 to {MAX_ALTERNATIVES} objects, "
            f"got {alternatives!r}"
        )
    parsed = []
    for alternative in alternatives:
        if (
            not isinstance(alternative, dict)
            or alternative.keys() != ALTERNATIVE_FIELDS
        ):
            raise ValueError(
                f"expected alternative fields {sorted(ALTERNATIVE_FIELDS)}, "
                f"got {alternative!r}"
            )
        parsed.append(_parse_accepted(alternative))
    return parsed


def _parse_accepted(entry: dict[str, Any]) -> AcceptedAnswer:
    numbers = frozenset(_parse_number(text) for text in _strings(entry, "numbers"))
    keywords = tuple(_strings(entry, "keywords"))
    if not numbers and not keywords:
        raise ValueError("expected at least one entry in 'numbers' or 'keywords'")
    return AcceptedAnswer(numbers, keywords)


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
