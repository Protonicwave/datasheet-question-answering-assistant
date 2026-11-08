import json
from collections.abc import Callable
from typing import Any

import anthropic
import httpx2
import pytest

from datasheet_assistant.answer import (
    MODEL,
    AnswerError,
    Unanswerable,
    answer_from_memory,
    answer_question,
)
from datasheet_assistant.retrieve import Chunk
from datasheet_assistant.verify import Answer, Citation

CHUNKS = [Chunk("bmp390", 7, "Sensor supply voltage VDD 1.65 1.8 3.6 V")]
QUESTION = "What is the maximum supply voltage of the BMP390?"

RECORDED_ANSWER = {
    "answerable": True,
    "answer": "The maximum supply voltage VDD is 3.6 V.",
    "citations": [
        {
            "datasheet": "bmp390",
            "page": 7,
            "quote": "Sensor supply voltage VDD 1.65 1.8 3.6 V",
        }
    ],
}


def message(text: str, stop_reason: str = "end_turn") -> dict[str, Any]:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": MODEL,
        "content": [{"type": "text", "text": text}],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }


def fake_client(
    respond: Callable[[httpx2.Request], httpx2.Response],
) -> anthropic.Anthropic:
    return anthropic.Anthropic(
        api_key="test-key",
        max_retries=0,
        http_client=anthropic.DefaultHttpxClient(
            transport=httpx2.MockTransport(respond)
        ),
    )


def replying(body: dict[str, Any], status: int = 200) -> anthropic.Anthropic:
    return fake_client(lambda request: httpx2.Response(status, json=body))


def test_parses_recorded_answer_into_citations() -> None:
    result = answer_question(
        replying(message(json.dumps(RECORDED_ANSWER))), QUESTION, CHUNKS
    )

    assert result == Answer(
        text="The maximum supply voltage VDD is 3.6 V.",
        citations=(Citation("bmp390", 7, "Sensor supply voltage VDD 1.65 1.8 3.6 V"),),
    )


def test_sends_question_and_excerpts_with_their_pages_and_answer_schema() -> None:
    sent: list[dict[str, Any]] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        sent.append(json.loads(request.content))
        return httpx2.Response(200, json=message(json.dumps(RECORDED_ANSWER)))

    answer_question(fake_client(respond), QUESTION, CHUNKS)

    [body] = sent
    prompt = body["messages"][0]["content"]
    assert body["model"] == MODEL
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert '<excerpt datasheet="bmp390" page="7">' in prompt
    assert "Sensor supply voltage VDD 1.65 1.8 3.6 V" in prompt
    assert QUESTION in prompt


def test_returns_unanswerable_when_model_says_excerpts_do_not_answer() -> None:
    reply = {"answerable": False, "answer": "", "citations": []}

    result = answer_question(replying(message(json.dumps(reply))), QUESTION, CHUNKS)

    assert result == Unanswerable()


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        json.dumps(["a list"]),
        json.dumps({"answer": "3.6 V", "citations": []}),
        json.dumps({**RECORDED_ANSWER, "answer": 3.6}),
        json.dumps({**RECORDED_ANSWER, "citations": [{"datasheet": "bmp390"}]}),
        json.dumps(
            {
                **RECORDED_ANSWER,
                "citations": [{"datasheet": "bmp390", "page": "7", "quote": "x"}],
            }
        ),
        json.dumps(
            {
                **RECORDED_ANSWER,
                "citations": [{"datasheet": "bmp390", "page": True, "quote": "x"}],
            }
        ),
    ],
)
def test_rejects_malformed_answer(text: str) -> None:
    with pytest.raises(AnswerError, match="malformed answer"):
        answer_question(replying(message(text)), QUESTION, CHUNKS)


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_incomplete_response_is_an_error_not_a_refusal(stop_reason: str) -> None:
    reply = message(json.dumps(RECORDED_ANSWER), stop_reason=stop_reason)

    with pytest.raises(AnswerError, match=stop_reason):
        answer_question(replying(reply), QUESTION, CHUNKS)


def test_api_failure_is_an_error() -> None:
    failure = {"type": "error", "error": {"type": "api_error", "message": "down"}}

    with pytest.raises(AnswerError, match="request failed"):
        answer_question(replying(failure, status=500), QUESTION, CHUNKS)


def test_memory_answer_sends_no_excerpts_and_parses_alike() -> None:
    sent: list[dict[str, Any]] = []
    reply = {"answerable": True, "answer": "3.6 V", "citations": []}

    def respond(request: httpx2.Request) -> httpx2.Response:
        sent.append(json.loads(request.content))
        return httpx2.Response(200, json=message(json.dumps(reply)))

    result = answer_from_memory(fake_client(respond), QUESTION)

    [body] = sent
    prompt = body["messages"][0]["content"]
    assert result == Answer(text="3.6 V", citations=())
    assert QUESTION in prompt
    assert "<excerpt" not in prompt
    assert "excerpts supplied" not in body["system"]


def test_memory_answer_failure_is_an_error() -> None:
    failure = {"type": "error", "error": {"type": "api_error", "message": "down"}}

    with pytest.raises(AnswerError, match="request failed"):
        answer_from_memory(replying(failure, status=500), QUESTION)
