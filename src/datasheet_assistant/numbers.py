"""Extracts the numbers a piece of text states, for comparison by value."""

import re
from decimal import Decimal

from datasheet_assistant.normalise import normalise

# A decimal value, or a hex literal as a lower-case string.
type Number = Decimal | str

# Digits directly after a letter or underscore belong to a name (BME280, I2C,
# SPI3, footnote markers), not a quantity. Letters after the digits are units
# (3.6V, 10ms) and do not stop a match. The exception is an "x" between
# dimensions: "2.5x3.0" states 2.5 and 3.0. No match starts after a digit and
# full stop, so a decimal is never split into fragments. A minus is a sign only when it
# does not follow a letter, digit or closing bracket, so "1.71-3.6" is a range.
NUMBER = re.compile(
    r"""
    (?:(?<![A-Za-z0-9_])(?<!\d\.)|(?<=\d[xX]))
    (?:
        (?P<hex>0[xX][0-9A-Fa-f]+)(?![A-Za-z0-9_])
      | (?P<decimal>(?:(?<![A-Za-z0-9_)\]])-)?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)
    )
    """,
    re.VERBOSE,
)


def extract_numbers(text: str) -> set[Number]:
    """Return the numbers in `text`, after normalisation.

    Decimals compare by value with sign (3.30 equals 3.3, -40 differs from
    40). A leading "+" or "±" is not part of the value. Hex literals compare
    as case-insensitive strings and never equal a decimal.
    """
    numbers: set[Number] = set()
    for match in NUMBER.finditer(normalise(text)):
        hex_literal = match.group("hex")
        if hex_literal is not None:
            numbers.add(hex_literal.lower())
        else:
            numbers.add(Decimal(match.group("decimal")))
    return numbers
