"""From a question to what the user is shown: retrieve, answer, verify."""

from collections.abc import Callable, Mapping, Sequence

from datasheet_assistant.answer import Unanswerable
from datasheet_assistant.retrieve import Chunk, Index
from datasheet_assistant.verify import Answer, Rejected, Verified, verify

# About 2,400 words of excerpts: room for a table and its footnotes from two
# or three places without burying the passage that answers.
TOP_CHUNKS = 8

type Answerer = Callable[[str, Sequence[Chunk]], Answer | Unanswerable]


def ask(
    question: str,
    index: Index,
    pages: Mapping[str, Sequence[str]],
    answerer: Answerer,
) -> Verified | Rejected | Unanswerable:
    """Answer `question` from the datasheets, showing only verified answers.

    Raises AnswerError if the answerer gives no usable answer.
    """
    reply = answer_from_excerpts(question, index, answerer)
    if isinstance(reply, Unanswerable):
        return reply
    return verify(reply, pages)


def answer_from_excerpts(
    question: str, index: Index, answerer: Answerer
) -> Answer | Unanswerable:
    """Retrieve excerpts for `question` and answer from them, unchecked.

    A question that shares no term with any excerpt is unanswerable without
    a model call. Raises AnswerError if the answerer gives no usable answer.
    """
    chunks = index.search(question, TOP_CHUNKS)
    if not chunks:
        return Unanswerable()
    return answerer(question, chunks)
