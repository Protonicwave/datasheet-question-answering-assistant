"""Download the datasheets, check their hashes and extract the text of each page."""

import hashlib
import json
import re
import tomllib
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium

MAX_PDF_BYTES = 50 * 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 60
USER_AGENT = "datasheet-assistant"

NAME_PATTERN = re.compile(r"[a-z0-9]+")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True, slots=True)
class Source:
    name: str
    url: str
    sha256: str


@dataclass(frozen=True, slots=True)
class ExtractedDatasheet:
    source: Source
    pages: list[str]


def load_sources(path: Path) -> list[Source]:
    """Parse the sources file. Raises ValueError naming the first invalid entry."""
    with path.open("rb") as file:
        entries = tomllib.load(file).get("datasheet", [])
    if not entries:
        raise ValueError(f"{path}: expected at least one [[datasheet]] entry")
    sources = [_parse_source(entry, index) for index, entry in enumerate(entries)]
    names = [source.name for source in sources]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ValueError(f"{path}: duplicate datasheet names {duplicates}")
    return sources


def _parse_source(entry: dict[str, object], index: int) -> Source:
    fields = {}
    for key in ("name", "url", "sha256"):
        value = entry.get(key)
        if not isinstance(value, str):
            raise ValueError(
                f"datasheet entry {index}: expected string '{key}', got {value!r}"
            )
        fields[key] = value
    source = Source(**fields)
    if not NAME_PATTERN.fullmatch(source.name):
        raise ValueError(
            f"datasheet entry {index}: expected lower-case name, got {source.name!r}"
        )
    if not source.url.startswith("https://"):
        raise ValueError(
            f"datasheet {source.name}: expected https URL, got {source.url!r}"
        )
    if not SHA256_PATTERN.fullmatch(source.sha256):
        raise ValueError(
            f"datasheet {source.name}: expected lower-case SHA-256, "
            f"got {source.sha256!r}"
        )
    return source


def download_pdf(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310 - URLs are checked to be https when loaded
    with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:  # noqa: S310 - as above
        content: bytes = response.read(MAX_PDF_BYTES + 1)
    if len(content) > MAX_PDF_BYTES:
        raise ValueError(f"{url}: download exceeds {MAX_PDF_BYTES} bytes")
    return content


def ingest(
    sources: Sequence[Source],
    pdf_dir: Path,
    pages_dir: Path,
    download: Callable[[str], bytes] = download_pdf,
) -> None:
    """Fetch, check and extract every source, then write one page file per datasheet.

    Nothing is written to `pages_dir` unless every datasheet succeeds, so the
    page set is never partial. Raises ValueError on a hash mismatch or a page
    without text, and OSError on a failed download.
    """
    extracted = [
        ExtractedDatasheet(
            source, extract_pages(_fetch(source, pdf_dir, download), source.name)
        )
        for source in sources
    ]
    pages_dir.mkdir(parents=True, exist_ok=True)
    for datasheet in extracted:
        record = {
            "datasheet": datasheet.source.name,
            "sha256": datasheet.source.sha256,
            "pages": [
                {"page": number, "text": text}
                for number, text in enumerate(datasheet.pages, start=1)
            ],
        }
        path = pages_dir / f"{datasheet.source.name}.json"
        path.write_text(
            json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8"
        )


def _fetch(source: Source, pdf_dir: Path, download: Callable[[str], bytes]) -> bytes:
    cached = pdf_dir / f"{source.name}.pdf"
    if cached.exists():
        content = cached.read_bytes()
        if _sha256(content) == source.sha256:
            return content
    content = download(source.url)
    actual = _sha256(content)
    if actual != source.sha256:
        raise ValueError(
            f"datasheet {source.name} from {source.url}: "
            f"expected SHA-256 {source.sha256}, got {actual}"
        )
    pdf_dir.mkdir(parents=True, exist_ok=True)
    cached.write_bytes(content)
    return content


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def extract_pages(pdf: bytes, name: str) -> list[str]:
    """Return the text of each page in order.

    Raises ValueError naming the first page without text.
    """
    document = pdfium.PdfDocument(pdf)
    try:
        pages = []
        for index in range(len(document)):
            text: str = (
                document[index].get_textpage().get_text_range().replace("\r\n", "\n")
            )
            if not text.strip():
                raise ValueError(
                    f"datasheet {name}: page {index + 1} has no text layer"
                )
            pages.append(text)
        return pages
    finally:
        document.close()
