import pytest

from datasheet_assistant.normalise import normalise, normalise_with_origins

CASES = [
    ("\ufb01lter coe\ufb03cient", "filter coefficient"),
    ("\u22124 °C", "-4 °C"),
    ("1.71\u20133.6 V", "1.71-3.6 V"),
    ("2.8 \u00b5A", "2.8 \u03bcA"),
    ("2.8 \u03bcA", "2.8 \u03bcA"),
    ("tempera-\nture", "temperature"),
    ("ultra-low\ufffepower", "ultralowpower"),
    ("ultra-low-power", "ultralowpower"),
    ("x- and y-axis", "x- and yaxis"),
    ("1.71-\n3.6 V", "1.71- 3.6 V"),
    ("Supply current\r\n  IDD,H \t1 Hz", "Supply current IDD,H 1 Hz"),
    ("  leading and trailing  ", "leading and trailing"),
    ("\u201cforced\u201d mode\u2019s", '"forced" mode\'s'),
    ("10\uf0e090\uf0e010 %RH", "10 90 10 %RH"),
    ("20\u202680 %RH", "20...80 %RH"),
    ("100 \u2126", "100 \u03a9"),
    ("", ""),
]
CASE_IDS = [
    "ligature",
    "unicode-minus",
    "en-dash",
    "micro-sign",
    "greek-mu",
    "line-end-hyphenation",
    "pdfium-line-break-hyphen",
    "hyphen-between-letters",
    "suspended-hyphen-kept",
    "range-dash-at-line-end",
    "whitespace",
    "strip",
    "curly-quotes",
    "symbol-font-glyph",
    "ellipsis-character",
    "ohm-sign",
    "empty",
]


@pytest.mark.parametrize(("raw", "expected"), CASES, ids=CASE_IDS)
def test_normalises(raw: str, expected: str) -> None:
    assert normalise(raw) == expected


def test_is_idempotent() -> None:
    text = "ultra-low\ufffepower \u22124 \u00b5A \ufb01lter"

    assert normalise(normalise(text)) == normalise(text)


@pytest.mark.parametrize(("raw", "expected"), CASES, ids=CASE_IDS)
def test_origin_tracking_form_matches_normalise(raw: str, expected: str) -> None:
    text, origins = normalise_with_origins(raw)

    assert text == expected
    assert len(origins) == len(text)


def test_origins_point_back_into_the_raw_text() -> None:
    raw = "  tempera-\nture \N{LATIN SMALL LIGATURE FI}lter"

    text, origins = normalise_with_origins(raw)

    assert text == "temperature filter"
    # The ligature expands to two characters, both from the one raw character.
    assert (
        "".join(raw[origin] for origin in origins)
        == "temperature \N{LATIN SMALL LIGATURE FI}\N{LATIN SMALL LIGATURE FI}lter"
    )
