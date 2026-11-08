# Datasheet assistant

Answers questions about Bosch Sensortec sensor datasheets. Every answer cites
the datasheet page and passage it came from, and is shown only when code has
verified it: the quote must appear on the cited page and every number in the
answer must appear in the quote. Otherwise the assistant says the datasheet
does not say.

## Install

Requires Python 3.12 or later and [uv](https://docs.astral.sh/uv/).

```sh
uv sync
```

## Run

Download the datasheets listed in `datasheets/sources.toml`, check their
hashes and extract the text of each page into `data/`:

```sh
uv run datasheet-assistant ingest
```

The PDFs are not part of this repository. `sources.toml` gives the URL and
SHA-256 of each one so the set can be reproduced exactly.

## Test

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run vulture src --min-confidence 80
```
