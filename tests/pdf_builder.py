"""Builds minimal PDFs for tests, so no binary fixtures are committed."""


def build_pdf(page_texts: list[str]) -> bytes:
    """One page per entry, showing its text in Helvetica.

    An empty entry gives a page with no text.
    """
    page_count = len(page_texts)
    kids = " ".join(f"{3 + 2 * index} 0 R" for index in range(page_count))
    font_id = 3 + 2 * page_count
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {page_count} >>",
    ]
    for index, text in enumerate(page_texts):
        stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET" if text else ""
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
            f"/Contents {4 + 2 * index} 0 R >>"
        )
        objects.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
    objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    output = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output += f"{number} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref_offset = len(output)
    output += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("latin-1")
    for offset in offsets:
        output += f"{offset:010d} 00000 n \n".encode("latin-1")
    trailer = f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
    output += f"{trailer}startxref\n{xref_offset}\n%%EOF\n".encode("latin-1")
    return bytes(output)
