from __future__ import annotations

from docx_redline.inspect import inspect_document
from docx_redline.ooxml import next_change_id, utc_timestamp
from docx_redline.package import DocxPackage
from docx_redline.text_ops import replace_text


def test_inspect_document_reports_location_and_counts(docx_factory) -> None:
    docx = docx_factory("doc.docx", [["First paragraph."], ["Second paragraph."]])
    package = DocxPackage(docx)
    document = package.xml("word/document.xml")

    infos = inspect_document(document)

    assert len(infos) == 2
    assert [info.location for info in infos] == ["body", "body"]
    assert infos[0].text == "First paragraph."
    assert infos[0].insertions == 0
    assert infos[0].deletions == 0


def test_inspect_document_marks_insertions_and_deletions(docx_factory) -> None:
    docx = docx_factory("doc.docx", [["Hello world."]])
    package = DocxPackage(docx)
    document = package.xml("word/document.xml")
    ids = next_change_id(document)
    replace_text(document, "world", "there", ids, "Tester", utc_timestamp())

    infos = inspect_document(document)

    assert infos[0].insertions == 1
    assert infos[0].deletions == 1
    assert "[DEL:world]" in infos[0].text
    assert "[INS:there]" in infos[0].text
