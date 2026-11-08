import struct
import zlib
from decimal import Decimal
from pathlib import Path

import pytest

from datasheet_assistant.pdf_pages import PdfPages
from tests.pdf_builder import build_pdf

# build_pdf pages are US Letter, 612 by 792 points.
PAGE_WIDTH_POINTS = 612
PAGE_HEIGHT_POINTS = 792


@pytest.fixture
def pdf_pages(tmp_path: Path) -> PdfPages:
    (tmp_path / "part.pdf").write_bytes(
        build_pdf(["Cover page", "Sleep current IDDSL 0.1 0.3 uA"])
    )
    return PdfPages(tmp_path)


def test_renders_the_page_as_a_png(pdf_pages: PdfPages) -> None:
    png = pdf_pages.render_png("part", 2)

    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    width, height = struct.unpack(">II", png[16:24])
    assert (width, height) == (PAGE_WIDTH_POINTS * 2, PAGE_HEIGHT_POINTS * 2)
    length = struct.unpack(">I", png[33:37])[0]
    assert png[37:41] == b"IDAT"
    rows = zlib.decompress(png[41 : 41 + length])
    assert len(rows) == height * (1 + width * 3)


def test_marks_the_quote_and_its_numbers_near_the_top(pdf_pages: PdfPages) -> None:
    marks = pdf_pages.mark("part", 2, "IDDSL 0.1 0.3 uA", {Decimal("0.1")})

    assert marks is not None
    (quote_box,) = marks.quote
    # build_pdf writes its text 72 points below the top of the page.
    assert 0.07 < quote_box.top < quote_box.bottom < 0.1
    assert [number.value for number in marks.numbers] == [Decimal("0.1")]
    (number_box,) = marks.numbers[0].boxes
    assert quote_box.left < number_box.left < number_box.right < quote_box.right


def test_quote_from_another_page_has_no_marks(pdf_pages: PdfPages) -> None:
    assert pdf_pages.mark("part", 1, "IDDSL 0.1 0.3 uA", set()) is None
