import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from datasheet_assistant.questions import (
    AcceptedAnswer,
    Expected,
    Question,
    load_questions,
)

PAGES = {
    "bme280": [
        "Operating range -40 to +85 °C",
        "Connecting SDO to GND results in slave address 1110110 (0x76)",
    ]
}

ANSWERABLE: dict[str, Any] = {
    "id": "bme280-i2c-address",
    "question": "What is the I2C address of the BME280 with SDO on GND?",
    "datasheet": "bme280",
    "answerable": True,
    "pages": [2],
    "numbers": ["0x76"],
    "keywords": ["slave address"],
}

UNANSWERABLE: dict[str, Any] = {
    "id": "bme280-price",
    "question": "What does the BME280 cost?",
    "datasheet": "bme280",
    "answerable": False,
}


def write(tmp_path: Path, *entries: Any) -> Path:
    path = tmp_path / "questions.jsonl"
    path.write_text(
        "\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8"
    )
    return path


def test_loads_answerable_and_unanswerable_questions(tmp_path: Path) -> None:
    questions = load_questions(write(tmp_path, ANSWERABLE, UNANSWERABLE), PAGES)

    assert questions == [
        Question(
            "bme280-i2c-address",
            ANSWERABLE["question"],
            "bme280",
            Expected((2,), (AcceptedAnswer(frozenset({"0x76"}), ("slave address",)),)),
        ),
        Question("bme280-price", "What does the BME280 cost?", "bme280", None),
    ]


def test_numbers_compare_by_value(tmp_path: Path) -> None:
    entry = {**ANSWERABLE, "pages": [1], "numbers": ["85.0"], "keywords": []}

    [question] = load_questions(write(tmp_path, entry), PAGES)

    assert question.expected is not None
    assert question.expected.accepted[0].numbers == {Decimal(85)}


def test_alternatives_follow_the_answer_as_stated(tmp_path: Path) -> None:
    entry = {
        **ANSWERABLE,
        "alternatives": [{"numbers": ["118"], "keywords": ["decimal"]}],
    }

    [question] = load_questions(write(tmp_path, entry), PAGES)

    assert question.expected is not None
    assert question.expected.accepted == (
        AcceptedAnswer(frozenset({"0x76"}), ("slave address",)),
        AcceptedAnswer(frozenset({Decimal(118)}), ("decimal",)),
    )


def test_skips_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "questions.jsonl"
    path.write_text(f"\n{json.dumps(UNANSWERABLE)}\n\n", encoding="utf-8")

    assert len(load_questions(path, PAGES)) == 1


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        ({**ANSWERABLE, "datasheet": "bmp999"}, "unknown datasheet 'bmp999'"),
        ({k: v for k, v in ANSWERABLE.items() if k != "pages"}, "expected fields"),
        ({**UNANSWERABLE, "pages": [1]}, "expected fields"),
        ({**ANSWERABLE, "extra": 1}, "expected fields"),
        ({**ANSWERABLE, "answerable": "yes"}, "boolean 'answerable'"),
        ({**ANSWERABLE, "id": "Has Spaces"}, "expected an id"),
        ({**ANSWERABLE, "question": "  "}, "non-empty string 'question'"),
        ({**ANSWERABLE, "pages": []}, "'pages'"),
        ({**ANSWERABLE, "pages": [3]}, "'pages'"),
        ({**ANSWERABLE, "pages": [True]}, "'pages'"),
        ({**ANSWERABLE, "numbers": ["3.6 to 4"]}, "one number"),
        ({**ANSWERABLE, "numbers": ["BME280"]}, "one number"),
        ({**ANSWERABLE, "numbers": [0x76]}, "'numbers'"),
        ({**ANSWERABLE, "numbers": [], "keywords": []}, "at least one entry"),
        ({**ANSWERABLE, "numbers": ["0x77"]}, "0x77 appear on none of pages"),
        ([ANSWERABLE], "expected an object"),
        ({**UNANSWERABLE, "alternatives": []}, "expected fields"),
        ({**ANSWERABLE, "alternatives": {}}, "'alternatives'"),
        ({**ANSWERABLE, "alternatives": None}, "'alternatives'"),
        ({**ANSWERABLE, "alternatives": []}, "'alternatives'"),
        ({**ANSWERABLE, "alternatives": [{"numbers": ["1"]}]}, "alternative fields"),
        (
            {**ANSWERABLE, "alternatives": [{"numbers": [], "keywords": []}]},
            "at least one entry",
        ),
    ],
)
def test_rejects_invalid_entry_naming_the_line(
    tmp_path: Path, entry: Any, message: str
) -> None:
    path = write(tmp_path, UNANSWERABLE, entry)

    with pytest.raises(ValueError, match="line 2") as raised:
        load_questions(path, PAGES)

    assert message in str(raised.value)


def test_rejects_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / "questions.jsonl"
    path.write_text("{not json\n", encoding="utf-8")

    with pytest.raises(ValueError, match="line 1"):
        load_questions(path, PAGES)


def test_rejects_duplicate_ids(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="duplicate question ids"):
        load_questions(write(tmp_path, UNANSWERABLE, UNANSWERABLE), PAGES)


def test_rejects_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "questions.jsonl"
    path.write_text("\n", encoding="utf-8")

    with pytest.raises(ValueError, match="at least one question"):
        load_questions(path, PAGES)
