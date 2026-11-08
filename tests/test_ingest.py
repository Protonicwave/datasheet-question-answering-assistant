import hashlib
import json
from pathlib import Path

import pytest

from datasheet_assistant.ingest import Source, extract_pages, ingest, load_sources
from tests.pdf_builder import build_pdf

URL = "https://example.com/part.pdf"


def make_source(pdf: bytes, name: str = "part") -> Source:
    return Source(
        name=name,
        url=f"https://example.com/{name}.pdf",
        sha256=hashlib.sha256(pdf).hexdigest(),
    )


def refuse_download(url: str) -> bytes:
    raise AssertionError(f"unexpected download of {url}")


def test_writes_one_record_per_page(tmp_path: Path) -> None:
    pdf = build_pdf(["Supply voltage 3.6 V", "Operating range -40 to 85"])

    ingest(
        [make_source(pdf)],
        tmp_path / "pdfs",
        tmp_path / "pages",
        download=lambda url: pdf,
    )

    record = json.loads((tmp_path / "pages" / "part.json").read_text(encoding="utf-8"))
    assert record["datasheet"] == "part"
    assert [page["page"] for page in record["pages"]] == [1, 2]
    assert "3.6 V" in record["pages"][0]["text"]
    assert "-40 to 85" in record["pages"][1]["text"]


def test_rejects_download_with_wrong_hash_naming_datasheet_and_url(
    tmp_path: Path,
) -> None:
    pdf = build_pdf(["Supply voltage 3.6 V"])
    source = make_source(pdf)

    with pytest.raises(
        ValueError, match=r"datasheet part from https://example.com/part.pdf"
    ):
        ingest(
            [source],
            tmp_path / "pdfs",
            tmp_path / "pages",
            download=lambda url: pdf + b"tampered",
        )


def test_writes_nothing_when_any_datasheet_fails(tmp_path: Path) -> None:
    good = build_pdf(["Supply voltage 3.6 V"])
    bad = build_pdf(["Operating range -40 to 85"])
    sources = [make_source(good, "good"), make_source(bad, "bad")]
    downloads = {sources[0].url: good, sources[1].url: bad + b"tampered"}

    with pytest.raises(ValueError, match="datasheet bad"):
        ingest(
            sources,
            tmp_path / "pdfs",
            tmp_path / "pages",
            download=downloads.__getitem__,
        )

    assert not (tmp_path / "pages").exists()


def test_uses_cached_pdf_when_hash_matches(tmp_path: Path) -> None:
    pdf = build_pdf(["Supply voltage 3.6 V"])
    (tmp_path / "pdfs").mkdir()
    (tmp_path / "pdfs" / "part.pdf").write_bytes(pdf)

    ingest(
        [make_source(pdf)],
        tmp_path / "pdfs",
        tmp_path / "pages",
        download=refuse_download,
    )

    assert (tmp_path / "pages" / "part.json").exists()


def test_downloads_again_when_cached_pdf_is_corrupt(tmp_path: Path) -> None:
    pdf = build_pdf(["Supply voltage 3.6 V"])
    (tmp_path / "pdfs").mkdir()
    (tmp_path / "pdfs" / "part.pdf").write_bytes(b"truncated")

    ingest(
        [make_source(pdf)],
        tmp_path / "pdfs",
        tmp_path / "pages",
        download=lambda url: pdf,
    )

    assert (tmp_path / "pdfs" / "part.pdf").read_bytes() == pdf


def test_rejects_page_without_text_naming_the_page() -> None:
    pdf = build_pdf(["Supply voltage 3.6 V", ""])

    with pytest.raises(ValueError, match="datasheet part: page 2 has no text layer"):
        extract_pages(pdf, "part")


VALID_ENTRY = f'name = "bme280"\nurl = "{URL}"\nsha256 = "{"a" * 64}"\n'


def write_sources(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "sources.toml"
    path.write_text(body, encoding="utf-8")
    return path


def test_loads_valid_sources(tmp_path: Path) -> None:
    path = write_sources(tmp_path, f"[[datasheet]]\n{VALID_ENTRY}")

    assert load_sources(path) == [Source(name="bme280", url=URL, sha256="a" * 64)]


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("", "expected at least one"),
        ('[[datasheet]]\nname = "bme280"\n', "expected string 'url'"),
        (
            f"[[datasheet]]\n{VALID_ENTRY.replace('bme280', 'BME 280')}",
            "expected lower-case name",
        ),
        (
            f"[[datasheet]]\n{VALID_ENTRY.replace('https', 'http')}",
            "expected https URL",
        ),
        (
            f"[[datasheet]]\n{VALID_ENTRY.replace('a' * 64, 'a' * 63)}",
            "expected lower-case SHA-256",
        ),
        (
            f"[[datasheet]]\n{VALID_ENTRY}[[datasheet]]\n{VALID_ENTRY}",
            "duplicate datasheet names",
        ),
    ],
)
def test_rejects_invalid_sources(tmp_path: Path, body: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        load_sources(write_sources(tmp_path, body))
