"""Renders datasheet pages to PNG and places quotes on them, using pdfium."""

import logging
import struct
import threading
import zlib
from collections.abc import Sequence, Set
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium

from datasheet_assistant.locate import (
    Box,
    TextSpan,
    line_boxes,
    locate_quote,
)
from datasheet_assistant.numbers import Number

logger = logging.getLogger(__name__)

# A4 is 595 points wide, so a scale of 2 gives an image about 1190 pixels
# wide: sharp beside the answer on a laptop screen, about 300 KB per page.
RENDER_SCALE = 2.0
PNG_COMPRESSION_LEVEL = 6
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_BMP_CODE_POINT = 0xFFFF


@dataclass(frozen=True, slots=True)
class NumberMarks:
    value: Number
    boxes: tuple[Box, ...]


@dataclass(frozen=True, slots=True)
class PageMarks:
    quote: tuple[Box, ...]
    numbers: tuple[NumberMarks, ...]


class PdfPages:
    """The datasheet PDFs that `ingest` downloaded.

    pdfium is not thread-safe, and a web server calls from several threads,
    so every pdfium call holds one lock. Callers pass a datasheet that
    exists and a page within its range.
    """

    def __init__(self, pdf_dir: Path) -> None:
        self._pdf_dir = pdf_dir
        self._lock = threading.Lock()

    def render_png(self, datasheet: str, page: int) -> bytes:
        """The page as a PNG image at RENDER_SCALE."""
        with self._lock:
            document = pdfium.PdfDocument(self._path(datasheet))
            try:
                bitmap = document[page - 1].render(
                    scale=RENDER_SCALE, rev_byteorder=True
                )
                if bitmap.mode != "RGB":
                    raise ValueError(f"expected an RGB bitmap, got {bitmap.mode!r}")
                pixels = bytes(bitmap.buffer)
                return _encode_png(bitmap.width, bitmap.height, bitmap.stride, pixels)
            finally:
                document.close()

    def mark(
        self, datasheet: str, page: int, quote: str, numbers: Set[Number]
    ) -> PageMarks | None:
        """Boxes around `quote` on the page and around each value of
        `numbers` inside it, or None if the quote is not found there."""
        with self._lock:
            document = pdfium.PdfDocument(self._path(datasheet))
            try:
                pdf_page = document[page - 1]
                text_page = pdf_page.get_textpage()
                text: str = text_page.get_text_range()
                offsets = utf16_offsets(text)
                if offsets[-1] != text_page.count_chars():
                    logger.warning(
                        "%s page %d: pdfium counts %d characters, text has %d units",
                        datasheet,
                        page,
                        text_page.count_chars(),
                        offsets[-1],
                    )
                    return None
                location = locate_quote(text, quote, numbers)
                if location is None:
                    return None
                size = pdf_page.get_size()
                return PageMarks(
                    _boxes(text_page, offsets, location.span, size),
                    tuple(
                        NumberMarks(
                            found.value,
                            _boxes(
                                text_page,
                                offsets,
                                TextSpan(found.start, found.end),
                                size,
                            ),
                        )
                        for found in location.numbers
                    ),
                )
            finally:
                document.close()

    def version(self, datasheet: str) -> str:
        """Changes whenever the datasheet's PDF file is replaced."""
        status = self._path(datasheet).stat()
        return f"{status.st_size}-{status.st_mtime_ns}"

    def _path(self, datasheet: str) -> Path:
        return self._pdf_dir / f"{datasheet}.pdf"


def utf16_offsets(text: str) -> list[int]:
    """The pdfium character index of each position in `text`, and of its end.

    pdfium counts characters in UTF-16 units, so a character outside the
    Basic Multilingual Plane, such as a mathematical italic letter, takes
    two indices while Python counts it once.
    """
    offsets = [0]
    for character in text:
        offsets.append(offsets[-1] + (2 if ord(character) > MAX_BMP_CODE_POINT else 1))
    return offsets


def _boxes(
    text_page: Any,
    offsets: Sequence[int],
    span: TextSpan,
    page_size: tuple[float, float],
) -> tuple[Box, ...]:
    """One box per line of the characters in `span`. `text_page` is a
    pdfium text page, which has no type information."""
    width, height = page_size
    return tuple(
        line_boxes(
            [
                _box(text_page.get_charbox(index), width, height)
                for index in range(offsets[span.start], offsets[span.end])
            ]
        )
    )


def _box(
    pdf_box: tuple[float, float, float, float], width: float, height: float
) -> Box:
    """A pdfium box (left, bottom, right, top in points from the bottom-left)
    as fractions from the top-left."""
    left, bottom, right, top = pdf_box
    return Box(left / width, 1 - top / height, right / width, 1 - bottom / height)


def _encode_png(width: int, height: int, stride: int, pixels: bytes) -> bytes:
    """Eight-bit RGB rows, each `stride` bytes long, as a PNG file."""
    row_bytes = width * 3
    rows = b"".join(
        b"\x00" + pixels[row * stride : row * stride + row_bytes]
        for row in range(height)
    )
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        PNG_SIGNATURE
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(rows, PNG_COMPRESSION_LEVEL))
        + _png_chunk(b"IEND", b"")
    )


def _png_chunk(kind: bytes, body: bytes) -> bytes:
    checksum = zlib.crc32(kind + body)
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", checksum)
