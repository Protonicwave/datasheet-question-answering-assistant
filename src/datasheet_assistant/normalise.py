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
