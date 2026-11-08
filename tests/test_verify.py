import pytest

from datasheet_assistant.verify import (
    Answer,
    Citation,
    Rejected,
    RejectionReason,
    Verified,
    verify,
)

PAGES = {
    "bme280": [
        "Bosch Sensortec | BME280 Data sheet 1 | 60",
        "Supply current IDD,H 1 Hz forced mode, \nhumidity and \ntemperature\n"
        "1.8 2.8 \u00b5A\nOperating range -40 25 85 °C",
        "Absolute accuracy tolerance AH 20\u202680 %RH, 25 °C, including "
        "hysteresis ±3 %RH. The device is ultra-low\ufffepower.",
    ],
    "bmp390": ["Supply voltage VDD 1.65 3.6 V"],
}

SUPPLY_QUOTE = "humidity and temperature 1.8 2.8 \u00b5A"


def answer(text: str, *citations: Citation) -> Answer:
    return Answer(text=text, citations=citations)


def cite(quote: str, page: int = 2, datasheet: str = "bme280") -> Citation:
    return Citation(datasheet=datasheet, page=page, quote=quote)


def rejection(result: Verified | Rejected) -> RejectionReason:
    assert isinstance(result, Rejected), result
    return result.reason


def test_accepts_true_quote_whose_numbers_cover_the_answer() -> None:
    claim = answer(
        "Typical humidity supply current is 1.8 \u03bcA.", cite(SUPPLY_QUOTE)
    )

    assert verify(claim, PAGES) == Verified(claim)


def test_accepts_quote_spanning_line_breaks_and_unicode_variants() -> None:
    quote = "Supply current IDD,H 1 Hz forced mode, humidity and temperature"

    assert isinstance(verify(answer("It is listed.", cite(quote)), PAGES), Verified)


def test_accepts_quote_with_ellipsis_that_is_on_the_page() -> None:
    claim = answer(
        "Accuracy is ±3 %RH between 20 and 80 %RH.",
        cite("tolerance AH 20...80 %RH, 25 °C, including hysteresis ±3 %RH", page=3),
    )

    assert isinstance(verify(claim, PAGES), Verified)


def test_accepts_hyphenated_spelling_of_word_broken_across_lines() -> None:
    claim = answer("It is low power.", cite("The device is ultra-low-power.", page=3))

    assert isinstance(verify(claim, PAGES), Verified)


def test_accepts_numbers_spread_across_several_citations() -> None:
    claim = answer(
        "Humidity draws 2.8 \u03bcA at most; the BMP390 runs from 1.65 V.",
        cite(SUPPLY_QUOTE),
        cite("Supply voltage VDD 1.65 3.6 V", page=1, datasheet="bmp390"),
    )

    assert isinstance(verify(claim, PAGES), Verified)


def test_rejects_answer_without_citations() -> None:
    assert rejection(verify(answer("It is 1.8 \u03bcA."), PAGES)) is (
        RejectionReason.NO_CITATIONS
    )


def test_rejects_unknown_datasheet() -> None:
    claim = answer("It is 1.8 \u03bcA.", cite(SUPPLY_QUOTE, datasheet="bme680"))

    assert rejection(verify(claim, PAGES)) is RejectionReason.UNKNOWN_DATASHEET


@pytest.mark.parametrize("page", [0, 4, -1])
def test_rejects_page_outside_the_datasheet(page: int) -> None:
    claim = answer("It is 1.8 \u03bcA.", cite(SUPPLY_QUOTE, page=page))

    assert rejection(verify(claim, PAGES)) is RejectionReason.PAGE_OUT_OF_RANGE


def test_rejects_quote_that_is_not_on_the_page() -> None:
    claim = answer(
        "It is 1.8 \u03bcA.", cite("humidity and temperature 1.8 3.0 \u00b5A")
    )

    assert rejection(verify(claim, PAGES)) is RejectionReason.QUOTE_NOT_ON_PAGE


def test_rejects_true_quote_cited_on_the_wrong_page() -> None:
    claim = answer("It is 1.8 \u03bcA.", cite(SUPPLY_QUOTE, page=3))

    assert rejection(verify(claim, PAGES)) is RejectionReason.QUOTE_NOT_ON_PAGE


def test_rejects_quote_shortened_with_an_ellipsis() -> None:
    claim = answer("It is 1.8 \u03bcA.", cite("Supply current ... 1.8 2.8 \u00b5A"))

    assert rejection(verify(claim, PAGES)) is RejectionReason.QUOTE_NOT_ON_PAGE


@pytest.mark.parametrize("quote", ["1.8 2.8 \u00b5A", "", "   "])
def test_rejects_quote_shorter_than_four_words(quote: str) -> None:
    claim = answer("It is 1.8 \u03bcA.", cite(quote))

    assert rejection(verify(claim, PAGES)) is RejectionReason.QUOTE_TOO_SHORT


def test_rejects_answer_number_absent_from_the_quote() -> None:
    claim = answer("Typical current is 1.9 \u03bcA.", cite(SUPPLY_QUOTE))

    result = verify(claim, PAGES)

    assert rejection(result) is RejectionReason.NUMBER_NOT_IN_QUOTES
    assert isinstance(result, Rejected)
    assert "1.9" in result.detail


def test_rejects_number_with_the_wrong_sign() -> None:
    claim = answer("The minimum is 40 °C.", cite("Operating range -40 25 85 °C"))

    assert rejection(verify(claim, PAGES)) is RejectionReason.NUMBER_NOT_IN_QUOTES


def test_rejects_number_from_a_unit_conversion() -> None:
    claim = answer("Typical current is 0.0018 mA.", cite(SUPPLY_QUOTE))

    assert rejection(verify(claim, PAGES)) is RejectionReason.NUMBER_NOT_IN_QUOTES


def test_ignores_part_numbers_in_the_answer() -> None:
    claim = answer("The BME280 draws 1.8 \u03bcA over I2C.", cite(SUPPLY_QUOTE))

    assert isinstance(verify(claim, PAGES), Verified)


def test_reports_the_first_failing_citation() -> None:
    claim = answer(
        "It is 1.8 \u03bcA.",
        cite(SUPPLY_QUOTE),
        cite(SUPPLY_QUOTE, datasheet="bme680"),
        cite("too short"),
    )

    assert rejection(verify(claim, PAGES)) is RejectionReason.UNKNOWN_DATASHEET


def test_rejects_wrong_second_dimension() -> None:
    pages = {"bmi270": ["14 pins, footprint 2.5x3.0mm, height 0.83mm"]}
    claim = answer(
        "The footprint is 2.5x4.0mm.",
        cite("14 pins, footprint 2.5x3.0mm, height 0.83mm", page=1, datasheet="bmi270"),
    )

    assert rejection(verify(claim, pages)) is RejectionReason.NUMBER_NOT_IN_QUOTES
