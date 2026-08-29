from __future__ import annotations

from lxml import etree

from docx_redline.cleanup import strip_format_revisions
from docx_redline.ooxml import NSMAP, w
from docx_redline.package import DocxPackage


def test_strip_format_revisions_removes_pprchange(docx_factory) -> None:
    docx = docx_factory("doc.docx", [["Some text."]])
    package = DocxPackage(docx)
    document = package.xml("word/document.xml")
    paragraph = document.xpath(".//w:p", namespaces=NSMAP)[0]
    ppr = etree.SubElement(paragraph, w("pPr"))
    paragraph.insert(0, ppr)
    change = etree.SubElement(ppr, w("pPrChange"))
    change.set(w("id"), "1")
    change.set(w("author"), "Tester")

    removed = strip_format_revisions(document)

    assert removed == 1
    assert not document.xpath(".//w:pPrChange", namespaces=NSMAP)
