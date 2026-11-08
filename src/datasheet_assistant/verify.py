"""Decides whether an answer is backed by the datasheet pages it cites."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from datasheet_assistant.normalise import normalise
from datasheet_assistant.numbers import Number, extract_numbers

# A shorter quote, such as "3.6 V", would appear on many pages and prove
# nothing about the claim it is attached to.
MIN_QUOTE_WORDS = 4


@dataclass(frozen=True, slots=True)
class Citation:
    datasheet: str
    page: int
    """1-based page number in the PDF."""
    quote: str


@dataclass(frozen=True, slots=True)
class Answer:
    text: str
    citations: tuple[Citation, ...]


class RejectionReason(StrEnum):
    NO_CITATIONS = "no_citations"
    UNKNOWN_DATASHEET = "unknown_datasheet"
    PAGE_OUT_OF_RANGE = "page_out_of_range"
    QUOTE_TOO_SHORT = "quote_too_short"
    QUOTE_NOT_ON_PAGE = "quote_not_on_page"
    NUMBER_NOT_IN_QUOTES = "number_not_in_quotes"


@dataclass(frozen=True, slots=True)
class Verified:
    answer: Answer


@dataclass(frozen=True, slots=True)
class Rejected:
    reason: RejectionReason
    detail: str


def verify(answer: Answer, pages: Mapping[str, Sequence[str]]) -> Verified | Rejected:
    """Accept `answer` only if every citation and every number checks out.

    `pages` maps a datasheet name to its page texts in order. Each quote must
    have at least MIN_QUOTE_WORDS words and appear, after normalisation, on
    the page it cites. Every number in the answer must appear in at least one
    of its quotes. Citations are checked in order and the first failure is
    returned.
    """
    if not answer.citations:
        return Rejected(RejectionReason.NO_CITATIONS, "answer cites no passage")
    for citation in answer.citations:
        rejected = _check_citation(citation, pages)
        if rejected is not None:
            return rejected

    quoted: set[Number] = set()
    for citation in answer.citations:
        quoted |= extract_numbers(citation.quote)
    unsupported = extract_numbers(answer.text) - quoted
    if unsupported:
        listed = ", ".join(sorted(str(number) for number in unsupported))
        return Rejected(
            RejectionReason.NUMBER_NOT_IN_QUOTES,
            f"answer states {listed}, which no quote contains",
        )
    return Verified(answer)


def _check_citation(
    citation: Citation, pages: Mapping[str, Sequence[str]]
) -> Rejected | None:
    location = f"{citation.datasheet} page {citation.page}"
    datasheet_pages = pages.get(citation.datasheet)
    if datasheet_pages is None:
        return Rejected(
            RejectionReason.UNKNOWN_DATASHEET,
            f"no datasheet named {citation.datasheet!r}",
        )
    if not 1 <= citation.page <= len(datasheet_pages):
        return Rejected(
            RejectionReason.PAGE_OUT_OF_RANGE,
            f"{location}: expected a page from 1 to {len(datasheet_pages)}",
        )
    quote = normalise(citation.quote)
    word_count = len(quote.split())
    if word_count < MIN_QUOTE_WORDS:
        return Rejected(
            RejectionReason.QUOTE_TOO_SHORT,
            f"{location}: quote has {word_count} words, "
            f"expected at least {MIN_QUOTE_WORDS}",
        )
    if quote not in normalise(datasheet_pages[citation.page - 1]):
        return Rejected(
            RejectionReason.QUOTE_NOT_ON_PAGE,
            f"{location}: quote not found: {citation.quote!r}",
        )
    return None
