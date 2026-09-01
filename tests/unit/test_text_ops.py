from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree

from docx_redline.errors import RedlineError
from docx_redline.ooxml import NSMAP, next_change_id, utc_timestamp, w
from docx_redline.package import DocxPackage
from docx_redline.text_ops import (
    apply_replace_batch,
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


# --- Minimal-diff redlines (default as_literal=False) -----------------------


def test_replace_default_diffs_full_sentences_to_minimal_span(docx_factory) -> None:
    docx = docx_factory("doc.docx", [["猫を見た。"]])
    package = _open(docx)
    document = package.xml("word/document.xml")
    ids = next_change_id(document)
    replace_text(document, "猫を見た。", "猫が見た。", ids, "Tester", utc_timestamp())
    paragraph = _paragraphs(document)[0]
    assert visible_text(paragraph) == "猫が見た。"
    deleted = "".join(paragraph.xpath(".//w:delText/text()", namespaces=NSMAP))
    inserted = "".join(paragraph.xpath(".//w:ins//w:t/text()", namespaces=NSMAP))
    assert deleted == "を"
    assert inserted == "が"


def test_replace_diff_handles_new_that_wholly_contains_old_as_a_suffix(
    docx_factory,
) -> None:
    # `new` = "hello " + `old` in full: the common *suffix* consumes all of
    # `old`, which must not leave old_diff without a run to anchor to.
    docx = docx_factory("doc.docx", [["Hello world."]])
    package = _open(docx)
    document = package.xml("word/document.xml")
    ids = next_change_id(document)
    replace_text(document, "world", "hello world", ids, "Tester", utc_timestamp())
    paragraph = _paragraphs(document)[0]
    assert visible_text(paragraph) == "Hello hello world."


def test_replace_as_literal_deletes_and_inserts_whole_strings(docx_factory) -> None:
    docx = docx_factory("doc.docx", [["猫を見た。"]])
    package = _open(docx)
    document = package.xml("word/document.xml")
    ids = next_change_id(document)
    replace_text(
        document,
        "猫を見た。",
        "猫が見た。",
        ids,
        "Tester",
        utc_timestamp(),
        as_literal=True,
    )
    paragraph = _paragraphs(document)[0]
    assert visible_text(paragraph) == "猫が見た。"
    deleted = "".join(paragraph.xpath(".//w:delText/text()", namespaces=NSMAP))
    inserted = "".join(paragraph.xpath(".//w:ins//w:t/text()", namespaces=NSMAP))
    assert deleted == "猫を見た。"
    assert inserted == "猫が見た。"


def test_replace_rejects_identical_old_and_new(docx_factory) -> None:
    docx = docx_factory("doc.docx", [["Hello world."]])
    package = _open(docx)
    document = package.xml("word/document.xml")
    ids = next_change_id(document)
    with pytest.raises(RedlineError, match="identical"):
        replace_text(document, "world", "world", ids, "Tester", utc_timestamp())


def test_replace_diff_span_still_rejects_heterogeneous_boundary(docx_factory) -> None:
    # The diffed middle span ("lo world" -> "LO WORLD", no shared prefix and
    # only "!" as a common suffix) still crosses the bold boundary, so it
    # must be refused exactly as a literal match would be.
    docx = docx_factory("doc.docx", [[("Hello ", ""), ("world", "<w:b/>"), ("!", "")]])
    package = _open(docx)
    document = package.xml("word/document.xml")
    ids = next_change_id(document)
    with pytest.raises(RedlineError, match="different.*formatting"):
        replace_text(document, "lo world!", "LO WORLD!", ids, "Tester", utc_timestamp())


# --- before/after context selectors ------------------------------------------


def test_replace_before_after_disambiguates_repeated_particle(docx_factory) -> None:
    docx = docx_factory("doc.docx", [["猫を見た。犬を見た。"]])
    package = _open(docx)
    document = package.xml("word/document.xml")
    ids = next_change_id(document)
    replace_text(
        document,
        "を",
        "が",
        ids,
        "Tester",
        utc_timestamp(),
        before="犬",
        after="見",
    )
    paragraph = _paragraphs(document)[0]
    assert visible_text(paragraph) == "猫を見た。犬が見た。"


def test_replace_before_after_with_no_match_reports_context(docx_factory) -> None:
    docx = docx_factory("doc.docx", [["one two three"]])
    package = _open(docx)
    document = package.xml("word/document.xml")
    ids = next_change_id(document)
    with pytest.raises(RedlineError, match="before='zzz'"):
        replace_text(
            document, "two", "TWO", ids, "Tester", utc_timestamp(), before="zzz"
        )


def test_replace_matches_across_proof_err_marker(docx_factory) -> None:
    docx = docx_factory("doc.docx", [["Hello ", "world"]])
    package = _open(docx)
    document = package.xml("word/document.xml")
    paragraph = _paragraphs(document)[0]
    first_run = paragraph.xpath("./w:r", namespaces=NSMAP)[0]
    proof_err = etree.Element(w("proofErr"))
    proof_err.set(w("type"), "spellStart")
    paragraph.insert(paragraph.index(first_run) + 1, proof_err)
    ids = next_change_id(document)
    replace_text(document, "lo wor", "LO WOR", ids, "Tester", utc_timestamp())
    assert visible_text(paragraph) == "HelLO WORld"


# --- replace-batch: source-relative planning ---------------------------------


def test_replace_batch_resolves_occurrence_against_source_not_progressive_state(
    docx_factory,
) -> None:
    # A naive sequential apply would replace pair 0's "cat" first, then
    # search for occurrence=1 of "cat" in the *already-edited* text and land
    # on the wrong (or a nonexistent) occurrence. Planning against the
    # untouched source means both pairs resolve to their original targets.
    docx = docx_factory("doc.docx", [["cat cat cat"]])
    package = _open(docx)
    document = package.xml("word/document.xml")
    ids = next_change_id(document)
    pairs = [
        {"old": "cat", "new": "dog", "occurrence": 0},
        {"old": "cat", "new": "fox", "occurrence": 2},
    ]
    total = apply_replace_batch(document, pairs, ids, "Tester", utc_timestamp())
    assert total == 2
    paragraph = _paragraphs(document)[0]
    assert visible_text(paragraph) == "dog cat fox"


def test_replace_batch_rejects_overlapping_pairs_without_writing(docx_factory) -> None:
    docx = docx_factory("doc.docx", [["Hello world."]])
    package = _open(docx)
    document = package.xml("word/document.xml")
    ids = next_change_id(document)
    pairs = [
        {"old": "Hello wo", "new": "HELLO WO"},
        {"old": "lo world", "new": "LO WORLD"},
    ]
    with pytest.raises(RedlineError, match="overlapping"):
        apply_replace_batch(document, pairs, ids, "Tester", utc_timestamp())
    paragraph = _paragraphs(document)[0]
    assert visible_text(paragraph) == "Hello world."
    assert _count(document, "del") == 0


def test_replace_batch_as_literal_is_per_pair(docx_factory) -> None:
    docx = docx_factory("doc.docx", [["猫を見た。犬を見た。"]])
    package = _open(docx)
    document = package.xml("word/document.xml")
    ids = next_change_id(document)
    pairs = [
        {"old": "猫を見た。", "new": "猫が見た。"},  # default: minimal diff
        {"old": "犬を見た。", "new": "犬が走った。", "as_literal": True},
    ]
    apply_replace_batch(document, pairs, ids, "Tester", utc_timestamp())
    paragraph = _paragraphs(document)[0]
    assert visible_text(paragraph) == "猫が見た。犬が走った。"
    # Pair 0 (diff mode): only the particle is deleted.
    # Pair 1 (as_literal): the whole original sentence is deleted.
    deleted_lengths = sorted(
        len(node.text or "")
        for node in document.xpath(".//w:delText", namespaces=NSMAP)
    )
    assert deleted_lengths == [1, 5]


def test_replace_batch_target_shifted_by_earlier_pair_in_same_paragraph(
    docx_factory,
) -> None:
    # Both pairs are in the same single-run paragraph; applying the earlier
    # (leftmost) pair first would shift where "three" starts if occurrence
    # resolution weren't planned up front against the source text.
    docx = docx_factory("doc.docx", [["one two three"]])
    package = _open(docx)
    document = package.xml("word/document.xml")
    ids = next_change_id(document)
    pairs = [
        {"old": "one", "new": "1"},
        {"old": "three", "new": "3"},
    ]
    apply_replace_batch(document, pairs, ids, "Tester", utc_timestamp())
    paragraph = _paragraphs(document)[0]
    assert visible_text(paragraph) == "1 two 3"


def test_replace_batch_targets_text_immediately_after_a_zero_width_separator(
    docx_factory,
) -> None:
    # A w:bookmarkStart contributes zero visible length, so the segment
    # after it starts exactly where the segment before it ends. Re-locating
    # this batch edit's segment at apply time must select the *following*
    # segment (where "world" actually is), not the preceding one.
    docx = docx_factory("doc.docx", [["Hello ", "world"]])
    package = _open(docx)
    document = package.xml("word/document.xml")
    paragraph = _paragraphs(document)[0]
    first_run = paragraph.xpath("./w:r", namespaces=NSMAP)[0]
    bookmark = etree.Element(w("bookmarkStart"))
    bookmark.set(w("id"), "0")
    bookmark.set(w("name"), "x")
    paragraph.insert(paragraph.index(first_run) + 1, bookmark)
    ids = next_change_id(document)
    pairs = [{"old": "world", "new": "planet"}]
    apply_replace_batch(document, pairs, ids, "Tester", utc_timestamp())
    assert visible_text(paragraph) == "Hello planet"


# --- Heterogeneous-run deletion-only edits ------------------------------------


def test_replace_deletes_across_heterogeneous_runs_preserving_each_run_formatting(
    docx_factory,
) -> None:
    docx = docx_factory(
        "doc.docx",
        [
            [
                ("before ", ""),
                ("bold", "<w:b/>"),
                ("underline", '<w:u w:val="single"/>'),
                (" after", ""),
            ]
        ],
    )
    package = _open(docx)
    document = package.xml("word/document.xml")
    ids = next_change_id(document)
    replace_text(document, "boldunderline", "", ids, "Tester", utc_timestamp())
    paragraph = _paragraphs(document)[0]
    assert visible_text(paragraph) == "before  after"
    bold_deletion = paragraph.xpath(
        ".//w:del/w:r[w:rPr/w:b]/w:delText/text()", namespaces=NSMAP
    )
    underline_deletion = paragraph.xpath(
        ".//w:del/w:r[w:rPr/w:u]/w:delText/text()", namespaces=NSMAP
    )
    assert bold_deletion == ["bold"]
    assert underline_deletion == ["underline"]


def test_replace_still_rejects_heterogeneous_insertion_even_as_deletion_adjacent(
    docx_factory,
) -> None:
    # A non-empty replacement spanning the same heterogeneous boundary must
    # still be refused - only a pure deletion (empty `new`) is allowed to
    # cross formatting boundaries.
    docx = docx_factory("doc.docx", [[("bold", "<w:b/>"), ("plain", "")]])
    package = _open(docx)
    document = package.xml("word/document.xml")
    ids = next_change_id(document)
    with pytest.raises(RedlineError, match="different.*formatting"):
        replace_text(
            document, "boldplain", "X", ids, "Tester", utc_timestamp(), as_literal=True
        )
