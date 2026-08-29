from __future__ import annotations

from pathlib import Path

from docx_redline import comments as comments_mod
from docx_redline.ooxml import NSMAP, utc_timestamp, w
from docx_redline.package import DocxPackage
from docx_redline.text_ops import find_paragraph


def _open(path: Path) -> DocxPackage:
    return DocxPackage(path)


def test_add_comment_creates_plumbing_from_scratch(docx_factory) -> None:
    docx = docx_factory("doc.docx", [["Please review this sentence."]])
    package = _open(docx)
    document = package.xml("word/document.xml")
    paragraph = find_paragraph(document, contains="review")

    comment_id = comments_mod.add_comment(
        package, paragraph, "Consider rewording.", author="Tester", when=utc_timestamp()
    )
    assert comment_id == 0

    comments = comments_mod.list_comments(package)
    assert len(comments) == 1
    assert comments[0].text == "Consider rewording."
    assert comments[0].author == "Tester"

    content_types = package.xml("[Content_Types].xml")
    assert content_types.xpath(
        "./ct:Override[@PartName='/word/comments.xml']", namespaces=NSMAP
    )
    rels = package.xml("word/_rels/document.xml.rels")
    assert rels.xpath(
        "./rel:Relationship[contains(@Type, 'comments')]", namespaces=NSMAP
    )

    anchors = document.xpath(".//w:commentRangeStart", namespaces=NSMAP)
    assert len(anchors) == 1
    assert anchors[0].get(w("id")) == "0"


def test_add_comment_reuses_existing_comments_part(docx_factory) -> None:
    docx = docx_factory("doc.docx", [["First target."], ["Second target."]])
    package = _open(docx)
    document = package.xml("word/document.xml")
    first = find_paragraph(document, contains="First")
    second = find_paragraph(document, contains="Second")
    comments_mod.add_comment(
        package, first, "one", author="Tester", when=utc_timestamp()
    )
    second_id = comments_mod.add_comment(
        package, second, "two", author="Tester", when=utc_timestamp()
    )
    assert second_id == 1
    assert len(comments_mod.list_comments(package)) == 2


def test_strip_comments_removes_everything(docx_factory) -> None:
    docx = docx_factory("doc.docx", [["Please review this sentence."]])
    package = _open(docx)
    document = package.xml("word/document.xml")
    paragraph = find_paragraph(document, contains="review")
    comments_mod.add_comment(
        package, paragraph, "Consider rewording.", author="Tester", when=utc_timestamp()
    )

    comments_mod.strip_comments(package)

    assert comments_mod.list_comments(package) == []
    assert not document.xpath(
        ".//w:commentRangeStart | .//w:commentRangeEnd | .//w:commentReference",
        namespaces=NSMAP,
    )
    assert not package.has_part(comments_mod.COMMENTS_PART)
    content_types = package.xml("[Content_Types].xml")
    assert not content_types.xpath(
        "./ct:Override[contains(@PartName, 'comments')]", namespaces=NSMAP
    )
