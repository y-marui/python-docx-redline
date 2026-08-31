from __future__ import annotations

from lxml import etree

from docx_redline.cleanup import accept_revisions, strip_format_revisions
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


def test_accept_revisions_unwraps_insertions_and_removes_deletions(
    docx_factory,
) -> None:
    docx = docx_factory("doc.docx", [["Before", " after."]])
    document = DocxPackage(docx).xml("word/document.xml")
    paragraph = document.xpath(".//w:p", namespaces=NSMAP)[0]
    first_run, second_run = paragraph.xpath("./w:r", namespaces=NSMAP)

    insertion = etree.Element(w("ins"))
    insertion.set(w("id"), "1")
    insertion.append(first_run)
    paragraph.insert(0, insertion)
    deletion = etree.Element(w("del"))
    deletion.set(w("id"), "2")
    deleted_run = etree.SubElement(deletion, w("r"))
    etree.SubElement(deleted_run, w("delText")).text = " deleted"
    paragraph.insert(1, deletion)

    accepted = accept_revisions(document)

    assert accepted.insertions == 1
    assert accepted.deletions == 1
    assert not document.xpath(".//w:ins | .//w:del", namespaces=NSMAP)
    assert paragraph.xpath("string(.)") == "Before after."
    assert second_run.getparent() is paragraph


def test_accept_revisions_removes_property_changes_and_empty_paragraphs(
    docx_factory,
) -> None:
    docx = docx_factory("doc.docx", [["Kept."], ["Removed."]])
    document = DocxPackage(docx).xml("word/document.xml")
    kept, removed = document.xpath(".//w:p", namespaces=NSMAP)
    ppr = etree.Element(w("pPr"))
    change = etree.SubElement(ppr, w("pPrChange"))
    change.set(w("id"), "1")
    kept.insert(0, ppr)
    deleted_run = removed.xpath("./w:r", namespaces=NSMAP)[0]
    deletion = etree.Element(w("del"))
    deletion.set(w("id"), "2")
    removed.remove(deleted_run)
    deletion.append(deleted_run)
    removed.append(deletion)

    accepted = accept_revisions(document)

    assert accepted.property_changes == 1
    assert accepted.empty_paragraphs == 1
    assert not document.xpath(
        ".//*[contains(local-name(), 'Change')]", namespaces=NSMAP
    )
    assert document.xpath("string(.//w:p)", namespaces=NSMAP) == "Kept."


def test_accept_revisions_keeps_existing_empty_paragraphs(docx_factory) -> None:
    docx = docx_factory("doc.docx", [[], ["Kept."]])
    document = DocxPackage(docx).xml("word/document.xml")

    accepted = accept_revisions(document)

    assert accepted.empty_paragraphs == 0
    assert len(document.xpath(".//w:p", namespaces=NSMAP)) == 2
