"""Scores what an arm showed the user against what the question expects."""

import re
from enum import StrEnum

from datasheet_assistant.normalise import normalise
from datasheet_assistant.numbers import extract_numbers
from datasheet_assistant.questions import Expected, Question
from datasheet_assistant.verify import Answer


class Score(StrEnum):
    CORRECT = "correct"
    WRONG = "wrong"
    CORRECT_REFUSAL = "correct_refusal"
    FALSE_REFUSAL = "false_refusal"
    UNPLACED = "unplaced"
    """The scorer cannot tell; the answer is left for a person to judge."""


def score(question: Question, shown: str | None) -> Score:
    """Score the answer text an arm showed, or None if it said the datasheet
    does not say.

    An answer is correct if it states every expected number and keyword, and
    wrong if it states numbers but none of the expected ones. Any answer to
    an unanswerable question is wrong. Anything in between is unplaced.
    """
    if shown is None:
        return Score.FALSE_REFUSAL if question.expected else Score.CORRECT_REFUSAL
    if question.expected is None:
        return Score.WRONG
    return _score_answer(question.expected, shown)


def _score_answer(expected: Expected, shown: str) -> Score:
    stated = extract_numbers(shown)
    text = normalise(shown).lower()
    if expected.numbers <= stated and all(
        _has_word(text, keyword) for keyword in expected.keywords
    ):
        return Score.CORRECT
    if expected.numbers and stated and not expected.numbers & stated:
        return Score.WRONG
    return Score.UNPLACED


def _has_word(text: str, keyword: str) -> bool:
    # Whole words only: "Pa" must not match inside "hPa".
    pattern = rf"(?<![a-z0-9]){re.escape(normalise(keyword).lower())}(?![a-z0-9])"
    return re.search(pattern, text) is not None


def cites_expected_page(question: Question, answer: Answer) -> bool | None:
    """Whether any citation is on an expected page of the question's datasheet.

    None for an unanswerable question, which has no expected page.
    """
    if question.expected is None:
        return None
    pages = question.expected.pages
    return any(
        citation.datasheet == question.datasheet and citation.page in pages
        for citation in answer.citations
    )
