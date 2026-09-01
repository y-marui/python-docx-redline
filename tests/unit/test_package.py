from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from lxml import etree

from docx_redline.package import DocxPackage


def test_save_rejects_same_path(docx_factory) -> None:
    docx = docx_factory("doc.docx", [["Text."]])
    package = DocxPackage(docx)
    with pytest.raises(ValueError, match="must differ"):
        package.save(docx)


def test_save_round_trips_edited_and_new_and_deleted_parts(
    docx_factory, tmp_path: Path
) -> None:
    docx = docx_factory("doc.docx", [["Text."]])
    package = DocxPackage(docx)

    document = package.xml("word/document.xml")
    document.set("edited", "true")

    new_root = etree.Element("extra")
    package.new_xml("word/extra.xml", new_root)

    package.delete_part("word/settings.xml")

    out = tmp_path / "out.docx"
    package.save(out)

    reopened = DocxPackage(out)
    assert reopened.xml("word/document.xml").get("edited") == "true"
    assert reopened.has_part("word/extra.xml")
    assert not reopened.has_part("word/settings.xml")


def test_save_preserves_bytes_of_a_searched_but_unedited_part(
    docx_factory, tmp_path: Path
) -> None:
    # Single-quoted attributes are valid XML but not what lxml's serializer
    # produces (it always uses double quotes) - a stand-in for the kind of
    # byte-level difference a real Word-authored part could have from
    # lxml's round-trip. This part is never mutated, only *parsed* (as
    # editable_text_parts()/xml() does for every part when searching across
    # a multi-part document), so save() must still emit its original bytes
    # rather than lxml's reserialization.
    docx = docx_factory("doc.docx", [["Text."]])
    header_bytes = (
        b"<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
        b"<w:hdr xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
        b"<w:p><w:r><w:t>Header text.</w:t></w:r></w:p></w:hdr>"
    )
    with zipfile.ZipFile(docx, "a") as archive:
        archive.writestr("word/header1.xml", header_bytes)

    package = DocxPackage(docx)
    package.xml("word/header1.xml")  # searched, e.g. by editable_text_parts()
    document = package.xml("word/document.xml")
    document.set("edited", "true")  # only this part is actually mutated

    out = tmp_path / "out.docx"
    package.save(out)

    assert DocxPackage(out).raw("word/header1.xml") == header_bytes
