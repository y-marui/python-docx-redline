from __future__ import annotations

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
