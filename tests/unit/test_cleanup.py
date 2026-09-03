from __future__ import annotations

import pytest
from lxml import etree

from docx_redline.cleanup import accept_revisions, strip_format_revisions
from docx_redline.errors import RedlineError
from docx_redline.ooxml import NSMAP, w
from docx_redline.package import DocxPackage


def _comment_reference_run(comment_id: str) -> etree._Element:
    run = etree.Element(w("r"))
    rpr = etree.SubElement(run, w("rPr"))
    etree.SubElement(rpr, w("rStyle")).set(w("val"), "CommentReference")
    etree.SubElement(run, w("commentReference")).set(w("id"), comment_id)
    return run


def _anchor_counts(document: etree._Element, comment_id: str) -> dict[str, int]:
    return {
        tag: len(
            document.xpath(f".//w:{tag}[@w:id=$id]", namespaces=NSMAP, id=comment_id)
        )
        for tag in ("commentRangeStart", "commentRangeEnd", "commentReference")
    }


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


def test_accept_revisions_leaves_comment_anchor_untouched_when_no_revision_overlaps(
    docx_factory,
) -> None:
    docx = docx_factory("doc.docx", [["Commented."], ["Unrelated."]])
    document = DocxPackage(docx).xml("word/document.xml")
    commented_paragraph, other_paragraph = document.xpath(".//w:p", namespaces=NSMAP)

    range_start = etree.Element(w("commentRangeStart"))
    range_start.set(w("id"), "5")
    commented_paragraph.insert(0, range_start)
    range_end = etree.Element(w("commentRangeEnd"))
    range_end.set(w("id"), "5")
    commented_paragraph.append(range_end)
    commented_paragraph.append(_comment_reference_run("5"))

    other_run = other_paragraph.xpath("./w:r", namespaces=NSMAP)[0]
    other_paragraph.remove(other_run)
    deletion = etree.Element(w("del"))
    deletion.set(w("id"), "1")
    deletion.append(other_run)
    other_paragraph.append(deletion)

    accepted = accept_revisions(document)

    assert accepted.deletions == 1
    assert _anchor_counts(document, "5") == {
        "commentRangeStart": 1,
        "commentRangeEnd": 1,
        "commentReference": 1,
    }
    assert commented_paragraph.find("w:commentRangeStart", namespaces=NSMAP) is (
        range_start
    )
    assert commented_paragraph.find("w:commentRangeEnd", namespaces=NSMAP) is range_end


def test_accept_revisions_relocates_endpoint_stranded_inside_accepted_deletion(
    docx_factory,
) -> None:
    docx = docx_factory("doc.docx", [["Kept text."]])
    document = DocxPackage(docx).xml("word/document.xml")
    paragraph = document.xpath(".//w:p", namespaces=NSMAP)[0]

    deletion = etree.Element(w("del"))
    deletion.set(w("id"), "1")
    range_start = etree.SubElement(deletion, w("commentRangeStart"))
    range_start.set(w("id"), "5")
    deleted_run = etree.SubElement(deletion, w("r"))
    etree.SubElement(deleted_run, w("delText")).text = "Deleted "
    paragraph.insert(0, deletion)

    range_end = etree.Element(w("commentRangeEnd"))
    range_end.set(w("id"), "5")
    paragraph.append(range_end)
    paragraph.append(_comment_reference_run("5"))

    accepted = accept_revisions(document)

    assert accepted.deletions == 1
    assert _anchor_counts(document, "5") == {
        "commentRangeStart": 1,
        "commentRangeEnd": 1,
        "commentReference": 1,
    }
    assert paragraph.xpath("string(.)") == "Kept text."
    assert list(paragraph)[0].tag == w("commentRangeStart")


def test_accept_revisions_relocates_both_endpoints_from_same_deletion(
    docx_factory,
) -> None:
    docx = docx_factory("doc.docx", [[]])
    document = DocxPackage(docx).xml("word/document.xml")
    paragraph = document.xpath(".//w:p", namespaces=NSMAP)[0]

    surviving_run = etree.SubElement(paragraph, w("r"))
    etree.SubElement(surviving_run, w("t")).text = "Kept."

    deletion = etree.Element(w("del"))
    deletion.set(w("id"), "1")
    range_start = etree.SubElement(deletion, w("commentRangeStart"))
    range_start.set(w("id"), "5")
    deleted_run = etree.SubElement(deletion, w("r"))
    etree.SubElement(deleted_run, w("delText")).text = "Deleted."
    range_end = etree.SubElement(deletion, w("commentRangeEnd"))
    range_end.set(w("id"), "5")
    paragraph.append(deletion)
    paragraph.append(_comment_reference_run("5"))

    accepted = accept_revisions(document)

    assert accepted.deletions == 1
    assert _anchor_counts(document, "5") == {
        "commentRangeStart": 1,
        "commentRangeEnd": 1,
        "commentReference": 1,
    }
    tags = [child.tag for child in paragraph]
    assert tags.index(w("commentRangeStart")) < tags.index(w("commentRangeEnd"))


def test_accept_revisions_removes_whole_comment_deleted_together(docx_factory) -> None:
    docx = docx_factory("doc.docx", [[]])
    document = DocxPackage(docx).xml("word/document.xml")
    paragraph = document.xpath(".//w:p", namespaces=NSMAP)[0]

    deletion = etree.Element(w("del"))
    deletion.set(w("id"), "1")
    range_start = etree.SubElement(deletion, w("commentRangeStart"))
    range_start.set(w("id"), "5")
    deleted_run = etree.SubElement(deletion, w("r"))
    etree.SubElement(deleted_run, w("delText")).text = "Deleted."
    range_end = etree.SubElement(deletion, w("commentRangeEnd"))
    range_end.set(w("id"), "5")
    deletion.append(_comment_reference_run("5"))
    paragraph.append(deletion)

    accepted = accept_revisions(document)

    assert accepted.deletions == 1
    assert accepted.removed_comment_ids == {"5"}
    assert _anchor_counts(document, "5") == {
        "commentRangeStart": 0,
        "commentRangeEnd": 0,
        "commentReference": 0,
    }


def test_accept_revisions_keeps_paragraph_emptied_only_by_relocated_anchor(
    docx_factory,
) -> None:
    docx = docx_factory("doc.docx", [["Comment starts here."], []])
    document = DocxPackage(docx).xml("word/document.xml")
    first_paragraph, second_paragraph = document.xpath(".//w:p", namespaces=NSMAP)

    range_start = etree.Element(w("commentRangeStart"))
    range_start.set(w("id"), "5")
    first_paragraph.insert(0, range_start)

    deletion = etree.Element(w("del"))
    deletion.set(w("id"), "1")
    range_end = etree.SubElement(deletion, w("commentRangeEnd"))
    range_end.set(w("id"), "5")
    deletion.append(_comment_reference_run("5"))
    second_paragraph.append(deletion)

    accepted = accept_revisions(document)

    assert accepted.deletions == 1
    assert accepted.empty_paragraphs == 0
    assert second_paragraph.getparent() is not None
    assert _anchor_counts(document, "5") == {
        "commentRangeStart": 1,
        "commentRangeEnd": 1,
        "commentReference": 1,
    }


def test_accept_revisions_raises_when_comment_reference_shares_run_with_other_content(
    docx_factory,
) -> None:
    docx = docx_factory("doc.docx", [["Kept."]])
    document = DocxPackage(docx).xml("word/document.xml")
    paragraph = document.xpath(".//w:p", namespaces=NSMAP)[0]

    range_start = etree.Element(w("commentRangeStart"))
    range_start.set(w("id"), "5")
    paragraph.append(range_start)
    range_end = etree.Element(w("commentRangeEnd"))
    range_end.set(w("id"), "5")
    paragraph.append(range_end)

    deletion = etree.Element(w("del"))
    deletion.set(w("id"), "1")
    mixed_run = etree.SubElement(deletion, w("r"))
    etree.SubElement(mixed_run, w("delText")).text = "Deleted"
    etree.SubElement(mixed_run, w("commentReference")).set(w("id"), "5")
    paragraph.append(deletion)

    with pytest.raises(RedlineError, match="5"):
        accept_revisions(document)


def test_accept_revisions_drops_duplicate_anchor_surviving_in_move_destination(
    docx_factory,
) -> None:
    """A commentRangeStart duplicated across a w:moveFrom/w:moveTo pair must
    not be relocated into a second copy alongside the one already surviving
    in the w:moveTo destination.
    """
    docx = docx_factory("doc.docx", [[]])
    document = DocxPackage(docx).xml("word/document.xml")
    paragraph = document.xpath(".//w:p", namespaces=NSMAP)[0]

    move_from = etree.SubElement(paragraph, w("moveFrom"))
    move_from.set(w("id"), "1")
    from_start = etree.SubElement(move_from, w("commentRangeStart"))
    from_start.set(w("id"), "5")
    moved_run = etree.SubElement(move_from, w("r"))
    etree.SubElement(moved_run, w("delText")).text = "Moved."

    move_to = etree.SubElement(paragraph, w("moveTo"))
    move_to.set(w("id"), "2")
    to_start = etree.SubElement(move_to, w("commentRangeStart"))
    to_start.set(w("id"), "5")
    kept_run = etree.SubElement(move_to, w("r"))
    etree.SubElement(kept_run, w("t")).text = "Moved."

    range_end = etree.Element(w("commentRangeEnd"))
    range_end.set(w("id"), "5")
    paragraph.append(range_end)
    paragraph.append(_comment_reference_run("5"))

    accepted = accept_revisions(document)

    assert accepted.deletions == 1
    assert accepted.insertions == 1
    assert accepted.removed_comment_ids == set()
    assert _anchor_counts(document, "5") == {
        "commentRangeStart": 1,
        "commentRangeEnd": 1,
        "commentReference": 1,
    }
    assert document.xpath(".//w:commentRangeStart", namespaces=NSMAP)[0] is to_start
