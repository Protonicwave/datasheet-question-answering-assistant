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

Ask a question. This needs an Anthropic API key in `ANTHROPIC_API_KEY`:

```sh
uv run datasheet-assistant ask "What is the maximum interface supply voltage VDDIO of the BMP390?"
```

The answer is printed with the datasheet, page and passage each citation
quotes. If the datasheets do not answer the question, or the answer fails
the check, it prints "The datasheet does not say." with the reason an answer
was withheld.

## Test

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run vulture src --min-confidence 80
```
