"""Paragraph text lookup and minimal, run-boundary-safe tracked replacement."""

from __future__ import annotations

from copy import deepcopy

from lxml import etree

from .errors import RedlineError
from .ooxml import NSMAP, IdAllocator, apply_bold, make_run, make_tracked_wrapper, w

Segment = list[tuple[etree._Element, etree._Element, str]]


def visible_text(paragraph: etree._Element) -> str:
    """Current (post-edit) text: w:t only, excludes w:delText."""
    return "".join(paragraph.xpath(".//w:t/text()", namespaces=NSMAP))


def find_paragraph(
    document: etree._Element, *, exact: str | None = None, contains: str | None = None
) -> etree._Element:
    if (exact is None) == (contains is None):
        raise RedlineError("specify exactly one of exact or contains")
    matches = []
    for paragraph in document.xpath(".//w:p", namespaces=NSMAP):
        text = visible_text(paragraph)
        if exact is not None and text == exact:
            matches.append(paragraph)
        elif contains is not None and contains in text:
            matches.append(paragraph)
    if len(matches) != 1:
        target = exact if exact is not None else contains
        raise RedlineError(
            f"expected exactly one paragraph matching {target!r}, found {len(matches)}"
        )
    return matches[0]


def _segments(paragraph: etree._Element) -> list[Segment]:
    """Maximal runs of consecutive plain <w:r><w:t> siblings, safe to splice."""
    segments: list[Segment] = []
    current: Segment = []
    for child in paragraph:
        text_nodes = (
            child.xpath("./w:t", namespaces=NSMAP) if child.tag == w("r") else []
        )
        if len(text_nodes) == 1:
            current.append((child, text_nodes[0], text_nodes[0].text or ""))
        elif child.tag == w("proofErr"):
            continue
        else:
            if current:
                segments.append(current)
                current = []
    if current:
        segments.append(current)
    return segments


def _find_matches(
    document: etree._Element, old: str, paragraph_contains: str | None
) -> list[tuple[etree._Element, Segment, int]]:
    matches: list[tuple[etree._Element, Segment, int]] = []
    for paragraph in document.xpath(".//w:p", namespaces=NSMAP):
        if paragraph_contains is not None and paragraph_contains not in visible_text(
            paragraph
        ):
            continue
        for segment in _segments(paragraph):
            combined = "".join(text for _, _, text in segment)
            start = 0
            while True:
                index = combined.find(old, start)
                if index < 0:
                    break
                matches.append((paragraph, segment, index))
                start = index + max(len(old), 1)
    return matches


def _apply_replacement(
    paragraph: etree._Element,
    segment: Segment,
    start: int,
    old: str,
    new: str,
    ids: IdAllocator,
    author: str,
    when: str,
    bold: bool | None,
) -> None:
    end = start + len(old)
    cursor = 0
    first_index = last_index = -1
    first_offset = last_offset = 0
    deleted_parts: list[tuple[str, etree._Element | None]] = []
    for run_index, (run, _, text) in enumerate(segment):
        run_start, run_end = cursor, cursor + len(text)
        overlap_start, overlap_end = max(start, run_start), min(end, run_end)
        if overlap_start < overlap_end:
            if first_index < 0:
                first_index, first_offset = run_index, overlap_start - run_start
            last_index, last_offset = run_index, overlap_end - run_start
            rpr = run.find("w:rPr", namespaces=NSMAP)
            deleted_parts.append(
                (
                    text[overlap_start - run_start : overlap_end - run_start],
                    deepcopy(rpr) if rpr is not None else None,
                )
            )
        cursor = run_end
    if first_index < 0:
        raise RedlineError("could not map replacement span onto runs")

    first_run, _, first_text = segment[first_index]
    last_run, _, last_text = segment[last_index]
    first_rpr = first_run.find("w:rPr", namespaces=NSMAP)
    first_rpr = deepcopy(first_rpr) if first_rpr is not None else None
    last_rpr = last_run.find("w:rPr", namespaces=NSMAP)
    last_rpr = deepcopy(last_rpr) if last_rpr is not None else None
    replacement_rpr = apply_bold(
        deepcopy(first_rpr) if first_rpr is not None else None, bold
    )

    nodes: list[etree._Element] = []
    before, after = first_text[:first_offset], last_text[last_offset:]
    if before:
        nodes.append(make_run(first_rpr, before))
    deletion = make_tracked_wrapper("del", ids.take(), author, when)
    for deleted_text, deleted_rpr in deleted_parts:
        deletion.append(make_run(deleted_rpr, deleted_text, deleted=True))
    nodes.append(deletion)
    if new:
        insertion = make_tracked_wrapper("ins", ids.take(), author, when)
        insertion.append(make_run(replacement_rpr, new))
        nodes.append(insertion)
    if after:
        nodes.append(make_run(last_rpr, after))

    first_run_index = paragraph.index(first_run)
    for run, _, _ in segment[first_index : last_index + 1]:
        paragraph.remove(run)
    for offset, node in enumerate(nodes):
        paragraph.insert(first_run_index + offset, node)


def replace_text(
    document: etree._Element,
    old: str,
    new: str,
    ids: IdAllocator,
    author: str,
    when: str,
    *,
    all_occurrences: bool = False,
    occurrence: int | None = None,
    bold: bool | None = None,
    paragraph_contains: str | None = None,
) -> int:
    """Replace `old` with `new` as a minimal tracked w:del+w:ins.

    By default exactly one match must exist across the whole document (a safety
    net against silently editing the wrong occurrence). Pass `occurrence` to pick
    one match by index, or `all_occurrences=True` to replace every match.
    """
    if not old:
        raise RedlineError("old text must not be empty")
    applied = 0
    while True:
        matches = _find_matches(document, old, paragraph_contains)
        if not matches:
            break
        if occurrence is not None:
            if applied > 0:
                break
            if not 0 <= occurrence < len(matches):
                raise RedlineError(
                    f"occurrence {occurrence} out of range: "
                    f"found {len(matches)} match(es) for {old!r}"
                )
            paragraph, segment, start = matches[occurrence]
        elif all_occurrences:
            paragraph, segment, start = matches[0]
        else:
            if len(matches) != 1:
                raise RedlineError(
                    f"expected exactly one match for {old!r}, found {len(matches)}; "
                    "use --occurrence or --all"
                )
            paragraph, segment, start = matches[0]
        _apply_replacement(paragraph, segment, start, old, new, ids, author, when, bold)
        applied += 1
        if not all_occurrences:
            break
    if applied == 0:
        raise RedlineError(f"text not found: {old!r}")
    return applied


def _first_run_properties(paragraph: etree._Element) -> etree._Element | None:
    for run in paragraph.xpath(".//w:r[w:t]", namespaces=NSMAP):
        text = "".join(run.xpath("./w:t/text()", namespaces=NSMAP))
        if not text.strip():
            continue
        rpr = run.find("w:rPr", namespaces=NSMAP)
        return deepcopy(rpr) if rpr is not None else None
    return None


def replace_paragraph_text(
    paragraph: etree._Element,
    new_text: str,
    ids: IdAllocator,
    author: str,
    when: str,
    *,
    bold: bool | None = None,
) -> None:
    """Replace a whole paragraph's content as a single tracked delete+insert."""
    old_text = visible_text(paragraph)
    old_rpr = _first_run_properties(paragraph)
    new_rpr = apply_bold(deepcopy(old_rpr) if old_rpr is not None else None, bold)
    for child in list(paragraph):
        if child.tag != w("pPr"):
            paragraph.remove(child)
    if old_text:
        deletion = make_tracked_wrapper("del", ids.take(), author, when)
        deletion.append(make_run(old_rpr, old_text, deleted=True))
        paragraph.append(deletion)
    insertion = make_tracked_wrapper("ins", ids.take(), author, when)
    insertion.append(make_run(new_rpr, new_text))
    paragraph.append(insertion)


def insert_paragraph_after(
    anchor: etree._Element,
    text: str,
    ids: IdAllocator,
    author: str,
    when: str,
    *,
    bold: bool | None = None,
) -> etree._Element:
    """Insert a new paragraph, tracked as an insertion, right after `anchor`."""
    parent = anchor.getparent()
    if parent is None:
        raise RedlineError("anchor paragraph has no parent")
    paragraph = etree.Element(w("p"))
    anchor_ppr = anchor.find("w:pPr", namespaces=NSMAP)
    if anchor_ppr is not None:
        paragraph.append(deepcopy(anchor_ppr))
    rpr = apply_bold(_first_run_properties(anchor), bold)
    insertion = make_tracked_wrapper("ins", ids.take(), author, when)
    insertion.append(make_run(rpr, text))
    paragraph.append(insertion)
    parent.insert(parent.index(anchor) + 1, paragraph)
    return paragraph
