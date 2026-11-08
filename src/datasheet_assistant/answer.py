"""Asks Claude to answer from retrieved excerpts, citing page and passage."""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import anthropic
from anthropic.types import MessageParam, OutputConfigParam

from datasheet_assistant.retrieve import Chunk
from datasheet_assistant.verify import Answer, Citation, Rejected

MODEL = "claude-sonnet-5-5"
MAX_OUTPUT_TOKENS = 16000
REQUEST_TIMEOUT_SECONDS = 120.0
# The SDK retries connection errors, 429 and 5xx with backoff.
MAX_RETRIES = 2

SYSTEM_PROMPT = """\
You answer questions about Bosch Sensortec sensor datasheets using only the \
excerpts supplied. Each excerpt is marked with its datasheet and page.

If the excerpts state the answer, set answerable to true, give a short \
answer and cite one to three passages. Each citation names the datasheet and \
page of its excerpt and quotes a passage of at least four words copied \
exactly from that excerpt, character for character, with no ellipses or \
edits. Every number in your answer must appear in one of your quotes: write \
numbers as the datasheet writes them, do not convert units, and do not \
repeat a number from the question unless a quote contains it. This covers \
numbers inside words too, such as "7-bit".

If the excerpts do not state the answer, set answerable to false, leave the \
answer empty and give no citations. Do not use knowledge from outside the \
excerpts."""

# Sent after an answer the check rejected. Without the last sentence, the
# cheapest way to pass would be to drop the value the question asks for.
REVISION_PROMPT = """\
The check rejected that answer: {rejection}. Answer the question again from \
the same excerpts under the same rules. Fix the cause: quote a passage that \
contains every number your answer states, copied exactly and at least four \
words long, or leave out a number that the question does not ask for. Do not \
drop a value the question asks for; if no excerpt states it, set answerable \
to false."""

# Same output schema as the excerpt prompt, so both arms parse alike.
MEMORY_PROMPT = """\
You answer questions about Bosch Sensortec sensor datasheets from what you \
know of them. No datasheet text is supplied.

If you know the answer, set answerable to true and give a short answer. If \
you do not know it, set answerable to false and leave the answer empty. In \
both cases give no citations."""

ANSWER_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "answerable": {"type": "boolean"},
        "answer": {"type": "string"},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "datasheet": {"type": "string"},
                    "page": {"type": "integer"},
                    "quote": {"type": "string"},
                },
                "required": ["datasheet", "page", "quote"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["answerable", "answer", "citations"],
    "additionalProperties": False,
}

OUTPUT_CONFIG: OutputConfigParam = {
    "effort": "high",
    "format": {"type": "json_schema", "schema": ANSWER_SCHEMA},
}


@dataclass(frozen=True, slots=True)
class Unanswerable:
    """The model found no answer in the excerpts."""


@dataclass(frozen=True, slots=True)
class RejectedAttempt:
    """An answer the check rejected, and why."""

    answer: Answer
    rejection: Rejected


class AnswerError(Exception):
    """The model gave no usable answer: the request failed, was refused or
    truncated, or the reply did not match the schema. Never a refusal on the
    merits, which is Unanswerable."""


def connect(api_key: str) -> anthropic.Anthropic:
    return anthropic.Anthropic(
        api_key=api_key, timeout=REQUEST_TIMEOUT_SECONDS, max_retries=MAX_RETRIES
    )


def answer_question(
    client: anthropic.Anthropic,
    question: str,
    chunks: Sequence[Chunk],
    rejected: Sequence[RejectedAttempt],
) -> Answer | Unanswerable:
    """Ask Claude to answer `question` from `chunks` alone.

    `rejected` holds the earlier answers to the same question that the check
    rejected, oldest first. Each is sent back as Claude's own turn followed
    by the rejection, so the new answer can address it.

    Raises AnswerError if no usable answer comes back.
    """
    messages: list[MessageParam] = [
        {"role": "user", "content": _prompt(question, chunks)}
    ]
    for attempt in rejected:
        rejection = f"{attempt.rejection.reason}: {attempt.rejection.detail}"
        messages.append({"role": "assistant", "content": _serialise(attempt.answer)})
        messages.append(
            {"role": "user", "content": REVISION_PROMPT.format(rejection=rejection)}
        )
    return _request(client, SYSTEM_PROMPT, messages)


def answer_from_memory(
    client: anthropic.Anthropic, question: str
) -> Answer | Unanswerable:
    """Ask Claude to answer `question` from what it already knows, with no
    excerpts. The baseline the excerpts and the check are measured against.

    Raises AnswerError if no usable answer comes back.
    """
    return _request(
        client, MEMORY_PROMPT, [{"role": "user", "content": f"Question: {question}"}]
    )


def _request(
    client: anthropic.Anthropic, system: str, messages: Sequence[MessageParam]
) -> Answer | Unanswerable:
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_OUTPUT_TOKENS,
            system=system,
            output_config=OUTPUT_CONFIG,
            messages=messages,
        )
    except anthropic.APIError as error:
        raise AnswerError(f"Claude API request failed: {error}") from error
    if response.stop_reason != "end_turn":
        raise AnswerError(
            f"expected a complete answer, got stop reason {response.stop_reason!r}"
        )
    text = "".join(block.text for block in response.content if block.type == "text")
    return _parse(text)


def _prompt(question: str, chunks: Sequence[Chunk]) -> str:
    excerpts = "\n\n".join(
        f'<excerpt datasheet="{chunk.datasheet}" page="{chunk.page}">\n'
        f"{chunk.text}\n</excerpt>"
        for chunk in chunks
    )
    return f"{excerpts}\n\nQuestion: {question}"


def _serialise(answer: Answer) -> str:
    """The answer as the JSON the model returned it in."""
    return json.dumps(
        {
            "answerable": True,
            "answer": answer.text,
            "citations": [
                {"datasheet": c.datasheet, "page": c.page, "quote": c.quote}
                for c in answer.citations
            ],
        },
        ensure_ascii=False,
    )


def _parse(text: str) -> Answer | Unanswerable:
    try:
        reply: Any = json.loads(text)
        if reply["answerable"] is False:
            return Unanswerable()
        if reply["answerable"] is not True or not isinstance(reply["answer"], str):
            raise TypeError("expected boolean 'answerable' and string 'answer'")
        citations = tuple(_parse_citation(entry) for entry in reply["citations"])
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise AnswerError(f"malformed answer {text!r}: {error}") from error
    return Answer(text=reply["answer"], citations=citations)


def _parse_citation(entry: Any) -> Citation:
    datasheet, page, quote = entry["datasheet"], entry["page"], entry["quote"]
    # bool is a subclass of int, and true is not a page number.
    if (
        not isinstance(datasheet, str)
        or type(page) is not int
        or not isinstance(quote, str)
    ):
        raise TypeError(f"expected string, integer and string in {entry!r}")
    return Citation(datasheet=datasheet, page=page, quote=quote)
