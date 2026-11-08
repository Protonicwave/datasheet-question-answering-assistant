"""Command-line entry point."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from datasheet_assistant.ingest import ingest, load_sources

SOURCES_PATH = Path("datasheets/sources.toml")
PDF_DIR = Path("data/pdfs")
PAGES_DIR = Path("data/pages")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="datasheet-assistant")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "ingest", help="download the datasheets and extract their page text"
    )
    parser.parse_args(argv)

    try:
        sources = load_sources(SOURCES_PATH)
        ingest(sources, PDF_DIR, PAGES_DIR)
    except (ValueError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"ingested {len(sources)} datasheets into {PAGES_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
