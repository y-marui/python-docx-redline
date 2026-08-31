from __future__ import annotations

from pathlib import Path

import pytest

from docx_redline.errors import RedlineError
from docx_redline.ooxml import NSMAP, next_change_id, utc_timestamp
from docx_redline.package import DocxPackage
from docx_redline.text_ops import (
    find_paragraph,
    insert_paragraph_after,
    replace_paragraph_text,
    replace_text,
    visible_text,
)


def _open(path: Path) -> DocxPackage:
    return DocxPackage(path)


def _paragraphs(node):
    return node.xpath(".//w:p", namespaces=NSMAP)


def _count(node, tag: str) -> int:
    return len(node.xpath(f".//w:{tag}", namespaces=NSMAP))


def test_replace_single_occurrence_succeeds(docx_factory) -> None:
    docx = docx_factory("doc.docx", [["Hello world."]])
    package = _open(docx)
    document = package.xml("word/document.xml")
    ids = next_change_id(document)
    count = replace_text(document, "world", "there", ids, "Tester", utc_timestamp())
    assert count == 1
    paragraph = _paragraphs(document)[0]
    assert visible_text(paragraph) == "Hello there."
    assert _count(document, "del") == 1
    assert _count(document, "ins") == 1


def test_replace_raises_when_multiple_matches(docx_factory) -> None:
    docx = docx_factory("doc.docx", [["a b a"]])
    package = _open(docx)
    document = package.xml("word/document.xml")
    ids = next_change_id(document)
    with pytest.raises(RedlineError, match="expected exactly one match"):
        replace_text(document, "a", "c", ids, "Tester", utc_timestamp())


def test_replace_raises_when_not_found(docx_factory) -> None:
    docx = docx_factory("doc.docx", [["a b c"]])
    package = _open(docx)
    document = package.xml("word/document.xml")
    ids = next_change_id(document)
    with pytest.raises(RedlineError, match="text not found"):
        replace_text(document, "zzz", "c", ids, "Tester", utc_timestamp())


def test_replace_by_occurrence_index(docx_factory) -> None:
    docx = docx_factory("doc.docx", [["cat dog cat"]])
    package = _open(docx)
    document = package.xml("word/document.xml")
    ids = next_change_id(document)
    replace_text(document, "cat", "fox", ids, "Tester", utc_timestamp(), occurrence=1)
    paragraph = _paragraphs(document)[0]
    assert visible_text(paragraph) == "cat dog fox"


def test_replace_all_occurrences(docx_factory) -> None:
    docx = docx_factory("doc.docx", [["cat dog cat"]])
    package = _open(docx)
    document = package.xml("word/document.xml")
    ids = next_change_id(document)
    count = replace_text(
        document, "cat", "fox", ids, "Tester", utc_timestamp(), all_occurrences=True
    )
    assert count == 2
    paragraph = _paragraphs(document)[0]
    assert visible_text(paragraph) == "fox dog fox"


def test_replace_across_run_boundaries(docx_factory) -> None:
    docx = docx_factory("doc.docx", [["軌道", "トルク", "の起源"]])
    package = _open(docx)
    document = package.xml("word/document.xml")
    ids = next_change_id(document)
    replace_text(document, "道トルクの", "道現象の", ids, "Tester", utc_timestamp())
    paragraph = _paragraphs(document)[0]
    assert visible_text(paragraph) == "軌道現象の起源"


def test_replace_across_homogeneous_run_boundaries_preserves_formatting(
    docx_factory,
) -> None:
    docx = docx_factory(
        "doc.docx",
        [[("軌道", "<w:b/>"), ("トルク", "<w:b/>"), ("の起源", "<w:b/>")]],
    )
    package = _open(docx)
    document = package.xml("word/document.xml")
    ids = next_change_id(document)
    replace_text(document, "道トルクの", "道現象の", ids, "Tester", utc_timestamp())
    paragraph = _paragraphs(document)[0]
    assert visible_text(paragraph) == "軌道現象の起源"
    insertion = paragraph.xpath(".//w:ins/w:r", namespaces=NSMAP)[0]
    assert insertion.xpath("./w:rPr/w:b", namespaces=NSMAP)


def test_replace_rejects_heterogeneous_bold_run_boundary(docx_factory) -> None:
    docx = docx_factory("doc.docx", [[("Hello ", ""), ("world", "<w:b/>"), ("!", "")]])
    package = _open(docx)
    document = package.xml("word/document.xml")
    ids = next_change_id(document)
    with pytest.raises(RedlineError, match="different.*formatting"):
        replace_text(document, "lo wor", "LO WOR", ids, "Tester", utc_timestamp())
    # No mutation on failure.
    paragraph = _paragraphs(document)[0]
    assert visible_text(paragraph) == "Hello world!"
    assert _count(document, "del") == 0
    assert _count(document, "ins") == 0


def test_replace_rejects_heterogeneous_italic_run_boundary(docx_factory) -> None:
    docx = docx_factory("doc.docx", [[("plain ", ""), ("slanted", "<w:i/>")]])
    package = _open(docx)
    document = package.xml("word/document.xml")
    ids = next_change_id(document)
    with pytest.raises(RedlineError, match="different.*formatting"):
        replace_text(document, "n sla", "N SLA", ids, "Tester", utc_timestamp())


def test_replace_rejects_heterogeneous_vertalign_run_boundary(docx_factory) -> None:
    docx = docx_factory(
        "doc.docx",
        [[("x", ""), ("2", '<w:vertAlign w:val="superscript"/>'), ("y", "")]],
    )
    package = _open(docx)
    document = package.xml("word/document.xml")
    ids = next_change_id(document)
    with pytest.raises(RedlineError, match="different.*formatting"):
        replace_text(document, "x2y", "z", ids, "Tester", utc_timestamp())


def test_replace_rejects_heterogeneous_character_style_run_boundary(
    docx_factory,
) -> None:
    docx = docx_factory(
        "doc.docx",
        [[("foo", ""), ("bar", '<w:rStyle w:val="Emphasis"/>')]],
    )
    package = _open(docx)
    document = package.xml("word/document.xml")
    ids = next_change_id(document)
    with pytest.raises(RedlineError, match="different.*formatting"):
        replace_text(document, "oobar", "OOBAR", ids, "Tester", utc_timestamp())


def test_replace_allows_match_across_equivalent_bold_encodings(docx_factory) -> None:
    # <w:b/>, w:val="1", and w:val="true" all mean the same "bold on" -
    # they must not be treated as a formatting boundary.
    docx = docx_factory(
        "doc.docx",
        [
            [
                ("foo", "<w:b/>"),
                ("bar", '<w:b w:val="1"/>'),
                ("baz", '<w:b w:val="true"/>'),
            ]
        ],
    )
    package = _open(docx)
    document = package.xml("word/document.xml")
    ids = next_change_id(document)
    replace_text(document, "oobarba", "OOBARBA", ids, "Tester", utc_timestamp())
    paragraph = _paragraphs(document)[0]
    assert visible_text(paragraph) == "fOOBARBAz"


def test_replace_allows_match_fully_within_one_formatted_run(docx_factory) -> None:
    docx = docx_factory(
        "doc.docx", [[("before ", ""), ("bold text here", "<w:b/>"), (" after", "")]]
    )
    package = _open(docx)
    document = package.xml("word/document.xml")
    ids = next_change_id(document)
    replace_text(document, "bold text", "BOLD TEXT", ids, "Tester", utc_timestamp())
    paragraph = _paragraphs(document)[0]
    assert visible_text(paragraph) == "before BOLD TEXT here after"
    insertion = paragraph.xpath(".//w:ins/w:r", namespaces=NSMAP)[0]
    assert insertion.xpath("./w:rPr/w:b", namespaces=NSMAP)


def test_replace_scopes_to_paragraph_contains(docx_factory) -> None:
    docx = docx_factory("doc.docx", [["target here"], ["target elsewhere"]])
    package = _open(docx)
    document = package.xml("word/document.xml")
    ids = next_change_id(document)
    replace_text(
        document,
        "target",
        "found",
        ids,
        "Tester",
        utc_timestamp(),
        paragraph_contains="elsewhere",
    )
    paragraphs = _paragraphs(document)
    assert visible_text(paragraphs[0]) == "target here"
    assert visible_text(paragraphs[1]) == "found elsewhere"


def test_replace_paragraph_text_replaces_whole_paragraph(docx_factory) -> None:
    docx = docx_factory("doc.docx", [["Old paragraph body."]])
    package = _open(docx)
    document = package.xml("word/document.xml")
    ids = next_change_id(document)
    paragraph = _paragraphs(document)[0]
    replace_paragraph_text(
        paragraph, "New paragraph body.", ids, "Tester", utc_timestamp()
    )
    assert visible_text(paragraph) == "New paragraph body."
    assert _count(paragraph, "del") == 1
    assert _count(paragraph, "ins") == 1


def test_insert_paragraph_after_anchor(docx_factory) -> None:
    docx = docx_factory("doc.docx", [["First."], ["Second."]])
    package = _open(docx)
    document = package.xml("word/document.xml")
    ids = next_change_id(document)
    anchor = find_paragraph(document, contains="First")
    insert_paragraph_after(anchor, "Inserted.", ids, "Tester", utc_timestamp())
    paragraphs = _paragraphs(document)
    assert [visible_text(p) for p in paragraphs] == ["First.", "Inserted.", "Second."]


def test_find_paragraph_ambiguous_match_raises(docx_factory) -> None:
    docx = docx_factory("doc.docx", [["same text"], ["same text"]])
    package = _open(docx)
    document = package.xml("word/document.xml")
    with pytest.raises(RedlineError, match="found 2"):
        find_paragraph(document, exact="same text")
