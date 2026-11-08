from decimal import Decimal

import pytest

from datasheet_assistant.questions import Expected, Question
from datasheet_assistant.score import Score, cites_expected_page, score
from datasheet_assistant.verify import Answer, Citation

ADDRESS = Question(
    "bme280-i2c-address",
    "What is the I2C address of the BME280 with SDO on GND?",
    "bme280",
    Expected((32,), frozenset({"0x76"}), ()),
)
RANGE = Question(
    "bme280-pressure-range",
    "What is the operating pressure range of the BME280?",
    "bme280",
    Expected((2,), frozenset({Decimal(300), Decimal(1100)}), ("hPa",)),
)
ACCURACY = Question(
    "bmp390-absolute-accuracy",
    "What is the typical absolute accuracy of the BMP390?",
    "bmp390",
    Expected((3,), frozenset({Decimal(50)}), ("Pa",)),
)
INTERFACES = Question(
    "bmm350-interfaces",
    "Which digital interfaces does the BMM350 offer?",
    "bmm350",
    Expected((2,), frozenset(), ("I2C", "I3C")),
)
PRICE = Question("bme280-price", "What does the BME280 cost?", "bme280", None)


@pytest.mark.parametrize(
    ("question", "shown", "expected"),
    [
        (ADDRESS, "The address is 0x76.", Score.CORRECT),
        (ADDRESS, "The address is 0X76 (1110110).", Score.CORRECT),
        (RANGE, "From 300 to 1100 hPa.", Score.CORRECT),
        (RANGE, "300.0 hPa to 1100 hPa", Score.CORRECT),
        (INTERFACES, "It offers i2c and I3C.", Score.CORRECT),
        (ADDRESS, "The address is 0x77.", Score.WRONG),
        (RANGE, "From 260 to 1260 hPa.", Score.WRONG),
        (PRICE, "It costs 2 dollars.", Score.WRONG),
        (PRICE, None, Score.CORRECT_REFUSAL),
        (ADDRESS, None, Score.FALSE_REFUSAL),
        (RANGE, "From 300 to 1250 hPa.", Score.UNPLACED),
        (RANGE, "From 300 to 1100 mbar.", Score.UNPLACED),
        (ACCURACY, "About 50 hPa.", Score.UNPLACED),
        (INTERFACES, "It offers I2C only.", Score.UNPLACED),
        (ADDRESS, "It depends on the SDO pin.", Score.UNPLACED),
    ],
)
def test_scores_what_was_shown(
    question: Question, shown: str | None, expected: Score
) -> None:
    assert score(question, shown) == expected


def test_cites_expected_page_when_any_citation_is_on_one() -> None:
    answer = Answer(
        "0x76",
        (
            Citation("bme280", 31, "the address is set by the SDO pin"),
            Citation("bme280", 32, "Connecting SDO to GND results in 0x76"),
        ),
    )

    assert cites_expected_page(ADDRESS, answer) is True


def test_citation_on_same_page_of_another_datasheet_does_not_count() -> None:
    answer = Answer("0x76", (Citation("bmp390", 32, "the address is 0x76 here"),))

    assert cites_expected_page(ADDRESS, answer) is False


def test_expected_page_does_not_apply_to_unanswerable_question() -> None:
    answer = Answer("2 dollars", (Citation("bme280", 1, "the price is 2 dollars"),))

    assert cites_expected_page(PRICE, answer) is None
