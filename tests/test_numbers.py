from decimal import Decimal

import pytest

from datasheet_assistant.numbers import extract_numbers


def d(*values: str) -> set[Decimal | str]:
    return {Decimal(value) for value in values}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Supply voltage 3.6 V", d("3.6")),
        ("3.30 V", d("3.3")),
        ("-40 25 85 °C", d("-40", "25", "85")),
        ("\u221240 °C", d("-40")),
        ("from +85 °C", d("85")),
        ("±0.5 hPa", d("0.5")),
        ("1.71-3.6 V", d("1.71", "3.6")),
        ("1.71 - 3.6 V", d("1.71", "3.6")),
        ("(-40)", d("-40")),
        ("scaled by 1e-3 or 2.5E+2", d("0.001", "250")),
        ("1.8V and 10ms", d("1.8", "10")),
        ("63%", d("63")),
        ("20\u202680 %RH", d("20", "80")),
        ("ends with 3.3.", d("3.3")),
        ("BME280 and BMI270", set()),
        ("I2C and SPI3", set()),
        ("Hysteresis2 HH", set()),
        ("footprint 2.5x3.0mm", d("2.5", "3.0")),
        ("2.5X3 mm", d("2.5", "3")),
        ("1.28 x 1.28 x 0.5 mm3", d("1.28", "0.5")),
        ("chip_id 0x60 at address 0X76", {"0x60", "0x76"}),
        ("0x6A equals 0x6a", {"0x6a"}),
        ("no numbers here", set()),
        ("", set()),
    ],
    ids=[
        "decimal",
        "trailing-zero",
        "signed-integers",
        "unicode-minus",
        "explicit-plus",
        "plus-minus-unsigned",
        "range-dash-is-not-a-sign",
        "spaced-range",
        "sign-after-bracket",
        "scientific",
        "attached-units",
        "percent",
        "ellipsis-range",
        "sentence-full-stop",
        "part-numbers-skipped",
        "interface-names-skipped",
        "footnote-markers-skipped",
        "dimensions",
        "dimensions-upper-case",
        "spaced-dimensions",
        "hex",
        "hex-case-insensitive",
        "none",
        "empty",
    ],
)
def test_extracts_numbers(text: str, expected: set[Decimal | str]) -> None:
    assert extract_numbers(text) == expected


def test_negative_and_positive_values_differ() -> None:
    assert extract_numbers("-40") != extract_numbers("40")


def test_hex_differs_from_its_decimal_value() -> None:
    assert extract_numbers("0x10") != extract_numbers("16")
