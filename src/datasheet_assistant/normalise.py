"""One text normaliser, shared by the quote check and search so both see one text."""

import re
import unicodedata

# pdfium writes U+FFFE where a word was hyphenated across a line break. It
# cannot tell a soft break ("consist-ing") from a real hyphen ("low-power"),
# so every hyphen between letters is dropped below and both spellings match.
PDFIUM_LINE_BREAK_HYPHEN = "\ufffe"

CHARACTER_MAP = str.maketrans(
    {
        PDFIUM_LINE_BREAK_HYPHEN: "-",
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2015": "-",
        "\u2212": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        # Glyph-substitution failures carry no text worth matching.
        "\ufffd": " ",
    }
)

# Symbol-font glyphs (arrows, bullets) extract as private-use code points.
PRIVATE_USE = re.compile("[\ue000-\uf8ff]")

# A hyphen between two letters, optionally followed by a line break. A hyphen
# followed by a space on the same line ("x- and y-axis") is kept.
HYPHEN_BETWEEN_LETTERS = re.compile(r"(?<=[^\W\d_])-(?:[ \t]*\r?\n[ \t]*)?(?=[^\W\d_])")

WHITESPACE = re.compile(r"\s+")


def normalise(text: str) -> str:
    """Return the matching form of `text`.

    NFKC (ligatures, the micro sign to Greek mu, the ohm sign to omega),
    dashes and the Unicode minus to "-", curly quotes to straight, hyphens
    between letters removed, whitespace collapsed. Idempotent.
    """
    text = text.translate(CHARACTER_MAP)
    text = unicodedata.normalize("NFKC", text)
    text = PRIVATE_USE.sub(" ", text)
    text = HYPHEN_BETWEEN_LETTERS.sub("", text)
    return WHITESPACE.sub(" ", text).strip()


def normalise_with_origins(text: str) -> tuple[str, list[int]]:
    """Return the matching form of `text` and, for each of its characters,
    the index in `text` it came from.

    Applies the steps of `normalise` one character at a time, so a span
    found in the matching form can be traced back to the original text.
    Agrees with `normalise` except where NFKC would combine characters
    across a boundary, such as a letter and a separate combining accent.
    """
    characters: list[str] = []
    origins: list[int] = []
    for index, character in enumerate(text):
        mapped = unicodedata.normalize("NFKC", character.translate(CHARACTER_MAP))
        for produced in PRIVATE_USE.sub(" ", mapped):
            characters.append(produced)
            origins.append(index)
    joined = "".join(characters)
    dropped = {
        position
        for match in HYPHEN_BETWEEN_LETTERS.finditer(joined)
        for position in range(match.start(), match.end())
    }

    result: list[str] = []
    result_origins: list[int] = []
    for position, character in enumerate(joined):
        if position in dropped:
            continue
        if character.isspace():
            if not result or result[-1] == " ":
                continue
            character = " "
        result.append(character)
        result_origins.append(origins[position])
    if result and result[-1] == " ":
        result.pop()
        result_origins.pop()
    return "".join(result), result_origins
