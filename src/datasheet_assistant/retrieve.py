"""BM25 search over datasheet text, in chunks that never span two pages."""

import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from datasheet_assistant.normalise import normalise

# Long enough to hold a table row with its heading, short enough that the
# retrieved excerpts for one question stay a few thousand tokens.
CHUNK_WORDS = 300

# Standard BM25 constants (Robertson and Zaragoza, 2009).
BM25_K1 = 1.2
BM25_B = 0.75

# Register and field names (ctrl_hum, osrs_h), decimals (3.6) and hex (0x76)
# stay whole, since questions hinge on them.
TOKEN = re.compile(r"[a-z0-9]+(?:[._][a-z0-9]+)*")


@dataclass(frozen=True, slots=True)
class Chunk:
    datasheet: str
    page: int
    """1-based page number in the PDF."""
    text: str


def chunk_pages(pages: Mapping[str, Sequence[str]]) -> list[Chunk]:
    """Split each page into chunks of whole lines, about CHUNK_WORDS words each.

    A chunk closes at the first line end after CHUNK_WORDS words, so it never
    cuts a line and never spans two pages.
    """
    chunks = []
    for datasheet, texts in pages.items():
        for page, text in enumerate(texts, start=1):
            lines: list[str] = []
            word_count = 0
            for line in text.splitlines():
                if not line.strip():
                    continue
                lines.append(line)
                word_count += len(line.split())
                if word_count >= CHUNK_WORDS:
                    chunks.append(Chunk(datasheet, page, "\n".join(lines)))
                    lines, word_count = [], 0
            if lines:
                chunks.append(Chunk(datasheet, page, "\n".join(lines)))
    return chunks


def _tokenise(text: str) -> list[str]:
    return TOKEN.findall(normalise(text).lower())


class Index:
    """BM25 over chunks."""

    def __init__(self, chunks: Sequence[Chunk]) -> None:
        self._chunks = list(chunks)
        self._term_counts = [Counter(_tokenise(chunk.text)) for chunk in self._chunks]
        self._datasheets = {chunk.datasheet for chunk in self._chunks}
        self._lengths = [sum(counts.values()) for counts in self._term_counts]
        self._mean_length = sum(self._lengths) / max(len(self._lengths), 1)
        document_frequency: Counter[str] = Counter()
        for counts in self._term_counts:
            document_frequency.update(counts.keys())
        total = len(self._chunks)
        self._idf = {
            term: math.log(1 + (total - frequency + 0.5) / (frequency + 0.5))
            for term, frequency in document_frequency.items()
        }

    def search(self, query: str, limit: int) -> list[Chunk]:
        """Return up to `limit` chunks sharing a term with `query`, best first.

        If `query` names any datasheet, only those datasheets are searched:
        every page header repeats the part number, so as a search term it
        barely separates one datasheet from another. Equal scores keep the
        order the chunks were given in.
        """
        if limit < 1:
            raise ValueError(f"expected a positive limit, got {limit}")
        query_terms = set(_tokenise(query))
        named = query_terms & self._datasheets
        terms = query_terms & self._idf.keys()
        scored = []
        for position, counts in enumerate(self._term_counts):
            if named and self._chunks[position].datasheet not in named:
                continue
            score = sum(
                self._term_score(term, counts[term], self._lengths[position])
                for term in terms
                if term in counts
            )
            if score > 0:
                scored.append((-score, position))
        scored.sort()
        return [self._chunks[position] for _, position in scored[:limit]]

    def _term_score(self, term: str, frequency: int, length: int) -> float:
        saturation = frequency * (BM25_K1 + 1)
        damping = frequency + BM25_K1 * (
            1 - BM25_B + BM25_B * length / self._mean_length
        )
        return self._idf[term] * saturation / damping
