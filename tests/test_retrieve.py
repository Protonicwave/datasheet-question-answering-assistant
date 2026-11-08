import pytest

from datasheet_assistant.retrieve import CHUNK_WORDS, Chunk, Index, chunk_pages


def words(count: int, word: str = "filler") -> str:
    return " ".join([word] * count)


def test_chunk_never_spans_two_pages() -> None:
    chunks = chunk_pages({"bme280": ["first page text", "second page text"]})

    assert chunks == [
        Chunk("bme280", 1, "first page text"),
        Chunk("bme280", 2, "second page text"),
    ]


def test_long_page_splits_at_line_ends_into_chunks_of_about_chunk_words() -> None:
    line = words(CHUNK_WORDS // 2)
    page = "\n".join([line] * 5)

    chunks = chunk_pages({"bme280": [page]})

    assert len(chunks) == 3
    assert all(chunk.page == 1 for chunk in chunks)
    assert " ".join(chunk.text for chunk in chunks).split() == page.split()


def test_blank_lines_produce_no_empty_chunks() -> None:
    chunks = chunk_pages({"bme280": ["\n\n  \n"]})

    assert chunks == []


def test_ranks_chunk_with_exact_parameter_name_first() -> None:
    index = Index(
        chunk_pages(
            {
                "bme280": [
                    "Operating range T Operational -40 25 85 °C temperature",
                    "Register 0xF2 ctrl_hum controls humidity oversampling osrs_h",
                    "Supply current IDD,T 1 Hz forced mode temperature measurement",
                ]
            }
        )
    )

    results = index.search("What does the osrs_h field in ctrl_hum set?", limit=3)

    assert results[0].page == 2


def test_part_number_in_question_restricts_search_to_that_datasheet() -> None:
    index = Index(
        chunk_pages(
            {
                "bma456": ["Supply voltage VDD 1.62 3.6 V supply voltage"],
                "bmp390": ["BMP390 Supply voltage VDD 1.65 3.6 V"],
            }
        )
    )

    results = index.search("supply voltage of the BMP390", limit=2)

    assert [chunk.datasheet for chunk in results] == ["bmp390"]


def test_question_naming_no_datasheet_searches_all() -> None:
    index = Index(
        chunk_pages({"bma456": ["Supply voltage VDD"], "bmp390": ["Supply voltage"]})
    )

    results = index.search("supply voltage", limit=2)

    assert {chunk.datasheet for chunk in results} == {"bma456", "bmp390"}


def test_returns_at_most_limit_chunks_and_none_without_shared_terms() -> None:
    index = Index(chunk_pages({"bme280": ["alpha beta", "alpha gamma", "alpha"]}))

    assert len(index.search("alpha", limit=2)) == 2
    assert index.search("unrelated", limit=2) == []


def test_ties_keep_page_order() -> None:
    index = Index(chunk_pages({"bme280": ["sensor one", "sensor two"]}))

    results = index.search("sensor", limit=2)

    assert [chunk.page for chunk in results] == [1, 2]


@pytest.mark.parametrize("limit", [0, -1])
def test_rejects_non_positive_limit(limit: int) -> None:
    index = Index(chunk_pages({"bme280": ["alpha"]}))

    with pytest.raises(ValueError, match="limit"):
        index.search("alpha", limit=limit)
