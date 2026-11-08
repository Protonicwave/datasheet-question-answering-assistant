# Datasheet assistant

Answers questions about Bosch Sensortec sensor datasheets. Every answer cites
the datasheet page and passage it came from, and is shown only when code has
verified it: the quote must appear on the cited page and every number in the
answer must appear in the quote. An answer that fails is sent back to the
model with the reason, once; if the revision does not pass, no answer is
shown.

The method and the held-out results are written up in
[docs/report/report.pdf](docs/report/report.pdf). A one-page guide for
engineers using the assistant is in [docs/guide/guide.pdf](docs/guide/guide.pdf).

## Install

On Windows, double-click `run.bat`. It installs uv and Node.js if they are
missing (uv with its official installer, Node.js LTS with winget), asks for
an Anthropic API key if `ANTHROPIC_API_KEY` is not set, installs the
dependencies, builds the web page, downloads the datasheets on first use and
opens the assistant in the browser. Steps already done are skipped.

Otherwise, the assistant requires Python 3.12 or later and
[uv](https://docs.astral.sh/uv/).

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
quotes. If the datasheets do not answer the question, it prints "The
datasheet does not say." If the answer and its revision both fail the
check, it prints "No verified answer." with the reason the answer was
withheld: the datasheet may still state it.

## Web page

The web page shows each answer beside the rendered datasheet page, with the
quoted passage highlighted; hovering a number in the answer marks it on the
page. A withheld answer is hidden, and the page its last draft cited is
shown with the passage outlined. Building the page needs Node.js 22 or
later:

```sh
cd web
npm ci
npm run build
cd ..
uv run datasheet-assistant serve
```

Then open <http://127.0.0.1:8000>. `serve` listens on this machine only and
takes `--port` to change the port. While working on the page, run
`npm run dev` in `web/` beside `serve` on its default port; Vite forwards
`/api` to port 8000.

## Evaluate

Run a question set through four arms: the model alone (A), the model
answering from retrieved excerpts (B), B's answers passed through the check
(C), and B's answers passed through the check with each rejected answer
sent back to the model, with the reason, for one revision (D). Each
arm runs three times by default. `eval/development.jsonl`
holds the questions whose results were read while building the assistant:

```sh
uv run datasheet-assistant evaluate --questions eval/development.jsonl --runs 3
```

`eval/held_out.jsonl` holds 50 further questions on the same datasheets,
40 answerable and 10 not, written after the assistant was finished and
run once with the code unchanged. Its results are the ones to quote.

Results go to a new directory under `eval/runs/`: every answer with its
citations (`answers.jsonl`), the score of each question per arm and run
(`scores.csv`), and the counts per arm (`summary.csv`, `summary.md`).
Answers scored `unplaced` state only some of the expected values, or none
of the numbers, and are left for a person to judge.

Each line of the question file is one JSON object. An answerable question
lists the numbers and keywords a correct answer must state and the pages
that state them; an unanswerable one has only `answerable: false`:

```json
{"id": "bmp390-max-vddio", "question": "What is the maximum interface supply voltage VDDIO of the BMP390?", "datasheet": "bmp390", "answerable": true, "pages": [3, 7], "numbers": ["3.6"], "keywords": []}
{"id": "bme280-unit-price", "question": "What is the unit price of the BME280 in quantities of 1,000?", "datasheet": "bme280", "answerable": false}
```

An answerable question may add `alternatives`, a list of objects with their
own `numbers` and `keywords`, for answers that give the same value another
way, such as `0.5 hPa` for `50 Pa`. An answer is correct if it states every
value of any one of these sets. Only the first set has to appear on the
listed pages.

## Report

The report's source is in `docs/report/`. Building it needs a TeX
distribution with LuaLaTeX and latexmk (MiKTeX or TeX Live); on Windows,
run latexmk from Git Bash, since MiKTeX ships no Perl. It also needs the
Erewhon, Source Sans 3 and IBM Plex Mono fonts and the `apsrev4-2`
bibliography style from REVTeX, which MiKTeX installs on first use. The
results figure is drawn from the held-out run with matplotlib, which
typesets its labels with LuaLaTeX:

```sh
uv run --group docs python docs/report/figures/results.py
cd docs/report
latexmk
cp build/main.pdf report.pdf
```

`report.pdf` is committed so the report can be read without TeX; rebuild
and commit it after changing the source. `laboratory.sty`,
`laboratory-base.sty` and `figures/laboratory.mplstyle` are unmodified
copies of a shared house style (version 2026/11/07); replace them whole
rather than editing them.

The guide in `docs/guide/` builds the same way: run `latexmk` there and
copy `build/main.pdf` to `guide.pdf`. It must stay on one page, which
`pdfinfo build/main.pdf` confirms, and its numbers must match the
report's.

## Test

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run vulture src --min-confidence 80
```

From `web/`:

```sh
npm test
npm run lint
npm run typecheck
npx knip
npm run build
```
