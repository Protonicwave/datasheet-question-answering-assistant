from pathlib import Path

import pytest

from datasheet_assistant.answer import RejectedAttempt, Unanswerable
from datasheet_assistant.cli import NO_VERIFIED_ANSWER, NOT_IN_DATASHEET, main, render
from datasheet_assistant.verify import (
    Answer,
    Citation,
    Rejected,
    RejectionReason,
    Verified,
)


def test_renders_verified_answer_with_each_citation() -> None:
    answer = Answer(
        "The address is 0x76.",
        (Citation("bme280", 32, "Connecting SDO to GND results in 0x76"),),
    )

    assert render(Verified(answer)) == (
        "The address is 0x76.\n\n"
        'bme280, page 32: "Connecting SDO to GND results in 0x76"'
    )


def test_renders_rejection_as_no_verified_answer_with_reason() -> None:
    rejected = RejectedAttempt(
        Answer("The address is 0x77.", ()),
        Rejected(
            RejectionReason.NUMBER_NOT_IN_QUOTES,
            "answer states 7, which no quote contains",
        ),
    )

    output = render(rejected)

    assert output.startswith(NO_VERIFIED_ANSWER)
    assert "0x77" not in output
    assert "answer states 7" in output


def test_renders_unanswerable_as_not_in_datasheet() -> None:
    assert render(Unanswerable()) == NOT_IN_DATASHEET


def test_ask_rejects_empty_question(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["ask", "  "]) == 1
    assert "expected a question" in capsys.readouterr().err


def test_ask_without_api_key_names_the_variable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    assert main(["ask", "What is the supply voltage?"]) == 1
    assert "ANTHROPIC_API_KEY is not set" in capsys.readouterr().err


def test_ask_before_ingest_says_to_ingest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.chdir(tmp_path)

    assert main(["ask", "What is the supply voltage?"]) == 1
    assert "run the ingest command first" in capsys.readouterr().err


def test_evaluate_without_api_key_names_the_variable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    assert main(["evaluate", "--questions", "q.jsonl"]) == 1
    assert "ANTHROPIC_API_KEY is not set" in capsys.readouterr().err


def test_evaluate_before_ingest_says_to_ingest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.chdir(tmp_path)

    assert main(["evaluate", "--questions", "q.jsonl", "--runs", "1"]) == 1
    assert "run the ingest command first" in capsys.readouterr().err


def test_evaluate_requires_a_question_file(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["evaluate"])

    assert exit_info.value.code == 2
    assert "--questions" in capsys.readouterr().err
