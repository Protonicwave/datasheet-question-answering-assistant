from decimal import Decimal

from datasheet_assistant.locate import Box, TextSpan, line_boxes, locate_quote

PAGE = "Table 1\r\nSleep current IDDSL 0.1 0.3 µA\r\nStandby current IDDSB 0.2 0.5 µA"


def spanned(text: str, span: TextSpan) -> str:
    return text[span.start : span.end]


def test_finds_the_quote_in_the_raw_page_text() -> None:
    location = locate_quote(PAGE, "Sleep current IDDSL 0.1 0.3 μA", set())

    assert location is not None
    assert spanned(PAGE, location.span) == "Sleep current IDDSL 0.1 0.3 µA"


def test_finds_a_quote_across_a_line_break_and_hyphenation() -> None:
    page = "the tempera-\r\nture sensor"

    location = locate_quote(page, "the temperature sensor", set())

    assert location is not None
    assert spanned(page, location.span) == page


def test_finds_only_the_requested_numbers_inside_the_quote() -> None:
    location = locate_quote(PAGE, "Sleep current IDDSL 0.1 0.3 µA", {Decimal("0.1")})

    assert location is not None
    assert [
        (found.value, PAGE[found.start : found.end]) for found in location.numbers
    ] == [(Decimal("0.1"), "0.1")]


def test_matches_numbers_by_value() -> None:
    location = locate_quote(PAGE, "IDDSB 0.2 0.5 µA", {Decimal("0.50")})

    assert location is not None
    assert [PAGE[found.start : found.end] for found in location.numbers] == ["0.5"]


def test_quote_not_on_the_page_is_not_found() -> None:
    assert locate_quote(PAGE, "Sleep current IDDSL 0.2", set()) is None


def test_empty_quote_is_not_found() -> None:
    assert locate_quote(PAGE, "  ", set()) is None


def test_characters_on_one_line_merge_into_one_box() -> None:
    boxes = [Box(0.1, 0.50, 0.12, 0.52), Box(0.12, 0.51, 0.14, 0.53)]

    assert line_boxes(boxes) == [Box(0.1, 0.50, 0.14, 0.53)]


def test_a_raised_quotation_mark_stays_on_its_line() -> None:
    boxes = [Box(0.1, 0.495, 0.11, 0.505), Box(0.11, 0.50, 0.2, 0.52)]

    assert line_boxes(boxes) == [Box(0.1, 0.495, 0.2, 0.52)]


def test_a_new_line_starts_a_new_box() -> None:
    first = Box(0.5, 0.50, 0.6, 0.52)
    wrapped = Box(0.1, 0.53, 0.2, 0.55)

    assert line_boxes([first, wrapped]) == [first, wrapped]


def test_a_character_back_at_the_left_starts_a_new_box() -> None:
    first = Box(0.5, 0.50, 0.6, 0.52)
    next_column = Box(0.1, 0.50, 0.2, 0.52)

    assert line_boxes([first, next_column]) == [first, next_column]


def test_empty_boxes_are_skipped() -> None:
    generated_space = Box(0.3, 0.5, 0.3, 0.5)

    assert line_boxes([generated_space]) == []


def test_a_repeated_quote_is_located_at_its_first_occurrence() -> None:
    page = "Supply voltage 3.6 V max. Supply voltage 3.6 V max."

    location = locate_quote(page, "Supply voltage 3.6 V", set())

    assert location is not None
    assert location.span == TextSpan(0, 20)
