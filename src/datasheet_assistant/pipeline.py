"""From a question to what the user is shown: retrieve, answer, verify."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from datasheet_assistant.answer import RejectedAttempt, Unanswerable
from datasheet_assistant.retrieve import Chunk, Index
from datasheet_assistant.verify import Answer, Rejected, Verified, verify

# About 2,400 words of excerpts: room for a table and its footnotes from two
# or three places without burying the passage that answers.
TOP_CHUNKS = 8

# Each revision is one more request on a question already answered once, so
# a rejected answer costs at most 1 + MAX_REVISIONS requests.
MAX_REVISIONS = 2

type Answerer = Callable[
    [str, Sequence[Chunk], Sequence[RejectedAttempt]], Answer | Unanswerable
]


@dataclass(frozen=True, slots=True)
class Checked:
    final: Verified | RejectedAttempt | Unanswerable
    """The last answer, verified or withheld, or the model's refusal."""
    revised: tuple[RejectedAttempt, ...]
    """Earlier answers sent back for revision, oldest first."""


def ask(
    question: str,
    index: Index,
    pages: Mapping[str, Sequence[str]],
    answerer: Answerer,
) -> Verified | Rejected | Unanswerable:
    """Answer `question` from the datasheets, showing only verified answers.

    Raises AnswerError if the answerer gives no usable answer.
    """
    chunks = index.search(question, TOP_CHUNKS)
    reply = answer_from_excerpts(question, chunks, answerer)
    if isinstance(reply, Unanswerable):
        return reply
    final = check_with_retry(question, chunks, reply, pages, answerer).final
    return final.rejection if isinstance(final, RejectedAttempt) else final


def answer_from_excerpts(
    question: str, chunks: Sequence[Chunk], answerer: Answerer
) -> Answer | Unanswerable:
    """Answer `question` from retrieved `chunks`, unchecked.

    With no chunks, the question shares no term with any excerpt and is
    unanswerable without a model call. Raises AnswerError if the answerer
    gives no usable answer.
    """
    if not chunks:
        return Unanswerable()
    return answerer(question, chunks, ())


def check_with_retry(
    question: str,
    chunks: Sequence[Chunk],
    first: Answer,
    pages: Mapping[str, Sequence[str]],
    answerer: Answerer,
) -> Checked:
    """Verify `first`; while the check rejects, send the answer back with the
    rejection, at most MAX_REVISIONS times. Every revision faces the same
    check, so a revision is shown only if it passes.

    Raises AnswerError if a revision request gives no usable answer.
    """
    revised: list[RejectedAttempt] = []
    answer = first
    for _ in range(MAX_REVISIONS):
        verdict = verify(answer, pages)
        if isinstance(verdict, Verified):
            return Checked(verdict, tuple(revised))
        revised.append(RejectedAttempt(answer, verdict))
        reply = answerer(question, chunks, tuple(revised))
        if isinstance(reply, Unanswerable):
            return Checked(reply, tuple(revised))
        answer = reply
    verdict = verify(answer, pages)
    if isinstance(verdict, Rejected):
        return Checked(RejectedAttempt(answer, verdict), tuple(revised))
    return Checked(verdict, tuple(revised))
