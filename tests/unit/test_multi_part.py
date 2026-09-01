"""Multi-part (headers/footers/footnotes/endnotes) inspect/replace coverage."""

from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree

from docx_redline.errors import RedlineError
from docx_redline.inspect import inspect_document, inspect_package
from docx_redline.ooxml import NSMAP, next_change_id, utc_timestamp
from docx_redline.package import DocxPackage
from docx_redline.text_ops import (
    apply_replace_batch,
    find_paragraph,
    replace_text,
    visible_text,
)

_W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def _build_multi_part_docx(docx_factory, tmp_path: Path) -> Path:
    """A .docx with a body, header, footer, footnote, endnote, and a comment -
    each containing distinguishable text, plus one shared phrase repeated in
    both the body and the header (used to test cross-part ambiguity).
    """
    base = docx_factory("base.docx", [["Body paragraph with shared phrase inside it."]])
    package = DocxPackage(base)
    header = etree.fromstring(
        f"<w:hdr {_W}><w:p><w:r><w:t>Header paragraph with shared phrase inside "
        f"it.</w:t></w:r></w:p></w:hdr>".encode()
    )
    footer = etree.fromstring(
        f"<w:ftr {_W}><w:p><w:r><w:t>Footer paragraph text.</w:t></w:r></w:p>"
        f"</w:ftr>".encode()
    )
    footnotes = etree.fromstring(
        f"<w:footnotes {_W}>"
        f'<w:footnote w:id="1"><w:p><w:r><w:t>Footnote body text.'
        f"</w:t></w:r></w:p></w:footnote></w:footnotes>".encode()
    )
    endnotes = etree.fromstring(
        f"<w:endnotes {_W}>"
        f'<w:endnote w:id="1"><w:p><w:r><w:t>Endnote body text.'
        f"</w:t></w:r></w:p></w:endnote></w:endnotes>".encode()
    )
    comments = etree.fromstring(
        f"<w:comments {_W}>"
        f'<w:comment w:id="1"><w:p><w:r><w:t>Comment body text.'
        f"</w:t></w:r></w:p></w:comment></w:comments>".encode()
    )
    package.new_xml("word/header1.xml", header)
    package.new_xml("word/footer1.xml", footer)
    package.new_xml("word/footnotes.xml", footnotes)
    package.new_xml("word/endnotes.xml", endnotes)
    package.new_xml("word/comments.xml", comments)
    out = tmp_path / "multi_part.docx"
    package.save(out)
    return out


def test_inspect_package_covers_every_editable_part(
    docx_factory, tmp_path: Path
) -> None:
    docx = _build_multi_part_docx(docx_factory, tmp_path)
    package = DocxPackage(docx)

    infos = inspect_package(package)

    parts_seen = {info.part for info in infos}
    assert parts_seen == {
        "word/document.xml",
        "word/header1.xml",
        "word/footer1.xml",
        "word/footnotes.xml",
        "word/endnotes.xml",
    }
    # comments.xml is intentionally out of scope (its own add-comment surface).
    assert "word/comments.xml" not in parts_seen
    # Index is renumbered sequentially across the combined listing.
    assert [info.index for info in infos] == list(range(1, len(infos) + 1))
    footnote_info = next(info for info in infos if info.part == "word/footnotes.xml")
    assert footnote_info.location == "footnote-1"
    endnote_info = next(info for info in infos if info.part == "word/endnotes.xml")
    assert endnote_info.location == "endnote-1"


def test_inspect_document_rejects_unsupported_root() -> None:
    settings = etree.fromstring(
        b'<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>'
    )
    with pytest.raises(ValueError, match="unsupported"):
        inspect_document(settings)


def test_replace_finds_and_edits_text_in_a_footer(docx_factory, tmp_path: Path) -> None:
    docx = _build_multi_part_docx(docx_factory, tmp_path)
    package = DocxPackage(docx)
    parts = package.editable_text_parts()
    ids = next_change_id([root for _, root in parts])
    replace_text(
        parts, "Footer paragraph", "Footer heading", ids, "Tester", utc_timestamp()
    )
    footer = package.xml("word/footer1.xml")
    paragraph = footer.xpath(".//w:p", namespaces=NSMAP)[0]
    assert visible_text(paragraph) == "Footer heading text."


def test_replace_finds_and_edits_text_in_a_footnote(
    docx_factory, tmp_path: Path
) -> None:
    docx = _build_multi_part_docx(docx_factory, tmp_path)
    package = DocxPackage(docx)
    parts = package.editable_text_parts()
    ids = next_change_id([root for _, root in parts])
    replace_text(
        parts,
        "Footnote body text.",
        "Footnote corrected text.",
        ids,
        "Tester",
        utc_timestamp(),
    )
    footnotes = package.xml("word/footnotes.xml")
    paragraph = footnotes.xpath(".//w:p", namespaces=NSMAP)[0]
    assert visible_text(paragraph) == "Footnote corrected text."


def test_replace_finds_and_edits_text_in_an_endnote(
    docx_factory, tmp_path: Path
) -> None:
    docx = _build_multi_part_docx(docx_factory, tmp_path)
    package = DocxPackage(docx)
    parts = package.editable_text_parts()
    ids = next_change_id([root for _, root in parts])
    replace_text(
        parts,
        "Endnote body text.",
        "Endnote corrected text.",
        ids,
        "Tester",
        utc_timestamp(),
    )
    endnotes = package.xml("word/endnotes.xml")
    paragraph = endnotes.xpath(".//w:p", namespaces=NSMAP)[0]
    assert visible_text(paragraph) == "Endnote corrected text."


def test_replace_ambiguous_across_parts_fails_without_part_hint(
    docx_factory, tmp_path: Path
) -> None:
    docx = _build_multi_part_docx(docx_factory, tmp_path)
    package = DocxPackage(docx)
    parts = package.editable_text_parts()
    ids = next_change_id([root for _, root in parts])
    with pytest.raises(RedlineError, match="found 2"):
        replace_text(
            parts, "shared phrase", "distinct phrase", ids, "Tester", utc_timestamp()
        )
    # Nothing written on failure.
    for name in ("word/document.xml", "word/header1.xml"):
        assert "distinct phrase" not in visible_text(
            package.xml(name).xpath(".//w:p", namespaces=NSMAP)[0]
        )


def test_replace_part_option_disambiguates(docx_factory, tmp_path: Path) -> None:
    docx = _build_multi_part_docx(docx_factory, tmp_path)
    package = DocxPackage(docx)
    parts = package.editable_text_parts()
    ids = next_change_id([root for _, root in parts])
    replace_text(
        parts,
        "shared phrase",
        "header-only phrase",
        ids,
        "Tester",
        utc_timestamp(),
        part="word/header1.xml",
    )
    header_paragraph = package.xml("word/header1.xml").xpath(
        ".//w:p", namespaces=NSMAP
    )[0]
    body_paragraph = package.xml("word/document.xml").xpath(".//w:p", namespaces=NSMAP)[
        0
    ]
    assert "header-only phrase" in visible_text(header_paragraph)
    assert "shared phrase" in visible_text(body_paragraph)


def test_find_paragraph_ambiguous_across_parts_reports_parts(
    docx_factory, tmp_path: Path
) -> None:
    docx = _build_multi_part_docx(docx_factory, tmp_path)
    package = DocxPackage(docx)
    parts = package.editable_text_parts()
    with pytest.raises(RedlineError, match="word/document.xml"):
        find_paragraph(parts, contains="shared phrase")


def test_replace_batch_applies_pairs_across_different_parts(
    docx_factory, tmp_path: Path
) -> None:
    docx = _build_multi_part_docx(docx_factory, tmp_path)
    package = DocxPackage(docx)
    parts = package.editable_text_parts()
    ids = next_change_id([root for _, root in parts])
    pairs = [
        {
            "old": "Footer paragraph text.",
            "new": "Footer heading text.",
            "part": "word/footer1.xml",
        },
        {
            "old": "Footnote body text.",
            "new": "Footnote corrected text.",
            "part": "word/footnotes.xml",
        },
    ]
    total = apply_replace_batch(parts, pairs, ids, "Tester", utc_timestamp())
    assert total == 2
    footer_paragraph = package.xml("word/footer1.xml").xpath(
        ".//w:p", namespaces=NSMAP
    )[0]
    footnote_paragraph = package.xml("word/footnotes.xml").xpath(
        ".//w:p", namespaces=NSMAP
    )[0]
    assert visible_text(footer_paragraph) == "Footer heading text."
    assert visible_text(footnote_paragraph) == "Footnote corrected text."
    # Unaffected parts are byte-identical to the source, after both go
    # through one save/reload cycle (fixture construction already saved
    # once, so this isn't just comparing against itself).
    out = tmp_path / "edited.docx"
    package.save(out)
    edited = DocxPackage(out)
    original = DocxPackage(docx)
    assert edited.raw("word/endnotes.xml") == original.raw("word/endnotes.xml")
    assert edited.raw("word/comments.xml") == original.raw("word/comments.xml")
    assert edited.raw("word/header1.xml") == original.raw("word/header1.xml")


def test_editable_text_parts_excludes_comments(docx_factory, tmp_path: Path) -> None:
    docx = _build_multi_part_docx(docx_factory, tmp_path)
    package = DocxPackage(docx)
    names = {name for name, _ in package.editable_text_parts()}
    assert "word/comments.xml" not in names
