"""Finds a verified quote, and the numbers in it, on a datasheet page."""

from collections.abc import Sequence, Set
from dataclasses import dataclass

from datasheet_assistant.normalise import normalise, normalise_with_origins
from datasheet_assistant.numbers import Number, number_spans


@dataclass(frozen=True, slots=True)
class TextSpan:
    """Character positions in a page's text, end exclusive."""

    start: int
    end: int


@dataclass(frozen=True, slots=True)
class NumberLocation:
    value: Number
    span: TextSpan


@dataclass(frozen=True, slots=True)
class QuoteLocation:
    span: TextSpan
    numbers: tuple[NumberLocation, ...]
    """The requested numbers that occur inside the quote, in page order."""


@dataclass(frozen=True, slots=True)
class Box:
    """A rectangle as fractions of the page's width and height, measured
    from the top-left corner, so it fits the page image at any scale."""

    left: float
    top: float
    right: float
    bottom: float


def locate_quote(
    page_text: str, quote: str, numbers: Set[Number]
) -> QuoteLocation | None:
    """Find `quote` in `page_text` the way the check matched it, after
    normalisation, and find each occurrence inside it of a value in
    `numbers`. Returns None if the quote is not on the page.
    """
    text, origins = normalise_with_origins(page_text)
    target = normalise(quote)
    start = text.find(target) if target else -1
    if start < 0:
        return None
    end = start + len(target)
    found = tuple(
        NumberLocation(
            span.value,
            TextSpan(origins[start + span.start], origins[start + span.end - 1] + 1),
        )
        for span in number_spans(text[start:end])
        if span.value in numbers
    )
    return QuoteLocation(TextSpan(origins[start], origins[end - 1] + 1), found)


def line_boxes(character_boxes: Sequence[Box]) -> list[Box]:
    """Merge the boxes of consecutive characters into one box per line.

    A character joins the current line when the two overlap vertically and
    it does not start left of the line, so a raised quotation mark stays on
    its line while a wrapped table cell starts a new one. Empty boxes, which
    pdfium gives for generated spaces and line breaks, are skipped.
    """
    lines: list[Box] = []
    for box in character_boxes:
        if box.right <= box.left or box.bottom <= box.top:
            continue
        if lines and box.top < lines[-1].bottom and box.bottom > lines[-1].top:
            line = lines[-1]
            if box.left >= line.left:
                lines[-1] = Box(
                    line.left,
                    min(line.top, box.top),
                    max(line.right, box.right),
                    max(line.bottom, box.bottom),
                )
                continue
        lines.append(box)
    return lines
