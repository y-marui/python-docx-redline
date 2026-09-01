"""Paragraph text lookup and minimal, run-boundary-safe tracked replacement."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from lxml import etree

from .errors import RedlineError
from .ooxml import (
    NSMAP,
    IdAllocator,
    RprSignature,
    apply_bold,
    make_run,
    make_tracked_wrapper,
    rpr_signature,
    w,
)

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


def _element_visible_len(element: etree._Element) -> int:
    return len("".join(element.xpath(".//w:t/text()", namespaces=NSMAP)))


def _segments(paragraph: etree._Element) -> list[tuple[int, Segment]]:
    """Maximal runs of consecutive plain <w:r><w:t> siblings, safe to splice.

    Each segment is paired with its start offset in the paragraph's visible
    text, so callers can translate a segment-local match position into a
    paragraph-absolute one (needed for `before`/`after` context matching).
    """
    segments: list[tuple[int, Segment]] = []
    current: Segment = []
    current_start = 0
    offset = 0
    for child in paragraph:
        text_nodes = (
            child.xpath("./w:t", namespaces=NSMAP) if child.tag == w("r") else []
        )
        if len(text_nodes) == 1:
            if not current:
                current_start = offset
            current.append((child, text_nodes[0], text_nodes[0].text or ""))
        elif child.tag == w("proofErr"):
            pass
        else:
            if current:
                segments.append((current_start, current))
                current = []
        offset += _element_visible_len(child)
    if current:
        segments.append((current_start, current))
    return segments


def _find_matches(
    document: etree._Element,
    old: str,
    paragraph_contains: str | None,
    before: str | None = None,
    after: str | None = None,
) -> list[tuple[etree._Element, Segment, int, int]]:
    """Find every match of `old`, as (paragraph, segment, local_start, absolute_start).

    `local_start` is relative to `segment`'s own combined text (what
    `_apply_replacement` expects); `absolute_start` is relative to the whole
    paragraph's visible text (stable across edits applied elsewhere in the
    same paragraph, unlike a segment reference - see `_segment_at`).
    """
    matches: list[tuple[etree._Element, Segment, int, int]] = []
    for paragraph in document.xpath(".//w:p", namespaces=NSMAP):
        paragraph_text = visible_text(paragraph)
        if paragraph_contains is not None and paragraph_contains not in paragraph_text:
            continue
        for segment_start, segment in _segments(paragraph):
            combined = "".join(text for _, _, text in segment)
            start = 0
            while True:
                index = combined.find(old, start)
                if index < 0:
                    break
                start = index + max(len(old), 1)
                absolute_start = segment_start + index
                absolute_end = absolute_start + len(old)
                if (
                    before is not None
                    and paragraph_text[
                        max(0, absolute_start - len(before)) : absolute_start
                    ]
                    != before
                ):
                    continue
                if (
                    after is not None
                    and paragraph_text[absolute_end : absolute_end + len(after)]
                    != after
                ):
                    continue
                matches.append((paragraph, segment, index, absolute_start))
    return matches


def _segment_at(paragraph: etree._Element, absolute_start: int) -> tuple[Segment, int]:
    """Re-locate the (segment, local_start) containing a paragraph-absolute offset.

    Used when applying a batch of edits within one paragraph: applying an
    edit rebuilds the runs it touches (even their untouched leading/trailing
    text becomes new run elements), which would leave any other planned
    edit's captured `Segment` pointing at removed elements. Absolute offsets
    of not-yet-applied edits stay valid across that rebuild as long as edits
    are applied right-to-left, so the segment is simply re-derived here.
    """
    for segment_start, segment in _segments(paragraph):
        combined_len = sum(len(text) for _, _, text in segment)
        if segment_start <= absolute_start <= segment_start + combined_len:
            return segment, absolute_start - segment_start
    raise RedlineError(
        "could not re-locate a planned batch edit after an earlier edit "
        "changed the paragraph"
    )


def _minimal_diff(old: str, new: str) -> tuple[int, str, str]:
    """Trim the common prefix/suffix of `old`/`new`, keeping only the differing middle.

    Used by the default (non-`as_literal`) matching mode so a pair that
    supplies full sentences records only the actual differing span as a
    tracked change, e.g. correcting a single particle inside an otherwise
    unchanged sentence. At least one character of `old` is always kept in
    the diff (even when `new` is a pure superset of `old`, e.g. an inserted
    character) so the result always anchors to an existing run to delete
    from, rather than requiring a separate zero-width-insertion code path.
    """
    max_common = min(len(old), len(new))
    prefix = 0
    while prefix < max_common and old[prefix] == new[prefix]:
        prefix += 1
    max_suffix = max_common - prefix
    suffix = 0
    while (
        suffix < max_suffix and old[len(old) - 1 - suffix] == new[len(new) - 1 - suffix]
    ):
        suffix += 1
    if prefix + suffix >= len(old):
        prefix = len(old) - suffix - 1
    return prefix, old[prefix : len(old) - suffix], new[prefix : len(new) - suffix]


def _diff_span(old: str, new: str, as_literal: bool) -> tuple[int, str, str]:
    """Resolve the (offset, old, new) triple to actually apply as a tracked change."""
    if old == new:
        raise RedlineError(f"old and new are identical: {old!r}; nothing to change")
    if as_literal:
        return 0, old, new
    return _minimal_diff(old, new)


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
    signatures: set[RprSignature] = set()
    for run_index, (run, _, text) in enumerate(segment):
        run_start, run_end = cursor, cursor + len(text)
        overlap_start, overlap_end = max(start, run_start), min(end, run_end)
        if overlap_start < overlap_end:
            if first_index < 0:
                first_index, first_offset = run_index, overlap_start - run_start
            last_index, last_offset = run_index, overlap_end - run_start
            rpr = run.find("w:rPr", namespaces=NSMAP)
            signatures.add(rpr_signature(rpr))
            deleted_parts.append(
                (
                    text[overlap_start - run_start : overlap_end - run_start],
                    deepcopy(rpr) if rpr is not None else None,
                )
            )
        cursor = run_end
    if first_index < 0:
        raise RedlineError("could not map replacement span onto runs")
    if new and len(signatures) > 1:
        raise RedlineError(
            f"cannot replace {old!r}: the match spans runs with different "
            "formatting (bold, italic, underline, font, character style, etc.). "
            "Auto-replacement across a formatting boundary is refused to avoid "
            "silently changing formatting outside the intended edit - narrow "
            "the match to a single formatting run, or edit this span manually."
        )

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
    leading, trailing = first_text[:first_offset], last_text[last_offset:]
    if leading:
        nodes.append(make_run(first_rpr, leading))
    deletion = make_tracked_wrapper("del", ids.take(), author, when)
    for deleted_text, deleted_rpr in deleted_parts:
        deletion.append(make_run(deleted_rpr, deleted_text, deleted=True))
    nodes.append(deletion)
    if new:
        insertion = make_tracked_wrapper("ins", ids.take(), author, when)
        insertion.append(make_run(replacement_rpr, new))
        nodes.append(insertion)
    if trailing:
        nodes.append(make_run(last_rpr, trailing))

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
    before: str | None = None,
    after: str | None = None,
    as_literal: bool = False,
) -> int:
    """Replace `old` with `new` as a minimal tracked w:del+w:ins.

    By default exactly one match must exist across the whole document (a safety
    net against silently editing the wrong occurrence). Pass `occurrence` to pick
    one match by index, `all_occurrences=True` to replace every match, or
    `paragraph_contains`/`before`/`after` to narrow the search to matches with
    that surrounding context (context text itself is never part of the tracked
    change).

    By default (`as_literal=False`) `old` and `new` may be full sentences; only
    their differing middle span is recorded as the tracked change, so a
    single-word or single-particle correction inside an unchanged sentence
    produces a minimal-diff redline instead of deleting and reinserting the
    whole sentence. Pass `as_literal=True` to delete the whole of `old` and
    insert the whole of `new` verbatim instead.

    A match that spans runs with different formatting is refused with a
    `RedlineError` before anything is written, rather than silently applying
    one run's formatting across the whole span - unless the edit is a pure
    deletion (empty `new`), in which case each deleted run keeps its own
    original formatting.
    """
    if not old:
        raise RedlineError("old text must not be empty")
    diff_offset, old_diff, new_diff = _diff_span(old, new, as_literal)
    applied = 0
    while True:
        matches = _find_matches(document, old, paragraph_contains, before, after)
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
            paragraph, segment, start, _ = matches[occurrence]
        elif all_occurrences:
            paragraph, segment, start, _ = matches[0]
        else:
            if len(matches) != 1:
                raise RedlineError(
                    f"expected exactly one match for {old!r}, found {len(matches)}; "
                    "use --occurrence or --all"
                )
            paragraph, segment, start, _ = matches[0]
        _apply_replacement(
            paragraph,
            segment,
            start + diff_offset,
            old_diff,
            new_diff,
            ids,
            author,
            when,
            bold,
        )
        applied += 1
        if not all_occurrences:
            break
    if applied == 0:
        context = ""
        if before is not None:
            context += f" with before={before!r}"
        if after is not None:
            context += f" with after={after!r}"
        raise RedlineError(f"text not found: {old!r}{context}")
    return applied


@dataclass
class _PlannedEdit:
    pair_index: int
    paragraph: etree._Element
    start: int  # paragraph-absolute; see `_segment_at`
    old: str
    new: str
    bold: bool | None


def _plan_batch_edits(
    document: etree._Element, pairs: list[dict[str, Any]]
) -> list[_PlannedEdit]:
    """Resolve every pair's target against the untouched document.

    All targets are located before any pair is applied, so an earlier pair's
    edit can never shift where a later pair's `occurrence` or context selector
    resolves to - the bug this replaces (sequential application against a
    progressively-mutated document).
    """
    planned: list[_PlannedEdit] = []
    for index, pair in enumerate(pairs):
        old = pair["old"]
        new = pair["new"]
        if not old:
            raise RedlineError(f"pair {index}: old text must not be empty")
        as_literal = pair.get("as_literal", False)
        try:
            diff_offset, old_diff, new_diff = _diff_span(old, new, as_literal)
        except RedlineError as error:
            raise RedlineError(f"pair {index} ({old!r}): {error}") from error
        matches = _find_matches(
            document,
            old,
            pair.get("paragraph_contains"),
            pair.get("before"),
            pair.get("after"),
        )
        occurrence = pair.get("occurrence")
        all_occurrences = pair.get("all", False)
        if occurrence is not None:
            if not 0 <= occurrence < len(matches):
                raise RedlineError(
                    f"pair {index} ({old!r}): occurrence {occurrence} out of range: "
                    f"found {len(matches)} match(es)"
                )
            selected = [matches[occurrence]]
        elif all_occurrences:
            if not matches:
                raise RedlineError(f"pair {index} ({old!r}): text not found")
            selected = matches
        else:
            if len(matches) != 1:
                raise RedlineError(
                    f"pair {index} ({old!r}): expected exactly one match, found "
                    f"{len(matches)}; use occurrence or all"
                )
            selected = matches
        for paragraph, _segment, _local_start, absolute_start in selected:
            planned.append(
                _PlannedEdit(
                    index,
                    paragraph,
                    absolute_start + diff_offset,
                    old_diff,
                    new_diff,
                    pair.get("bold"),
                )
            )
    return planned


def _group_by_paragraph(
    planned: list[_PlannedEdit],
) -> dict[int, list[_PlannedEdit]]:
    grouped: dict[int, list[_PlannedEdit]] = {}
    for edit in planned:
        grouped.setdefault(id(edit.paragraph), []).append(edit)
    return grouped


def _check_no_overlaps(grouped: dict[int, list[_PlannedEdit]]) -> None:
    for edits in grouped.values():
        ordered = sorted(edits, key=lambda edit: edit.start)
        for previous, current in zip(ordered, ordered[1:], strict=False):
            if current.start < previous.start + len(previous.old):
                raise RedlineError(
                    f"pair {previous.pair_index} and pair {current.pair_index} "
                    "target overlapping text in the same paragraph"
                )


def apply_replace_batch(
    document: etree._Element,
    pairs: list[dict[str, Any]],
    ids: IdAllocator,
    author: str,
    when: str,
) -> int:
    """Apply a batch of tracked replacements, resolved against the source state.

    Every pair's target is located before any pair is applied (see
    `_plan_batch_edits`), and edits within the same paragraph are then applied
    right-to-left so an earlier (in document order) not-yet-applied edit's
    already-resolved position is never shifted by a later one. Two pairs
    whose resolved spans overlap fail the whole batch before anything is
    written.
    """
    planned = _plan_batch_edits(document, pairs)
    grouped = _group_by_paragraph(planned)
    _check_no_overlaps(grouped)
    applied = 0
    for edits in grouped.values():
        for edit in sorted(edits, key=lambda edit: edit.start, reverse=True):
            segment, local_start = _segment_at(edit.paragraph, edit.start)
            _apply_replacement(
                edit.paragraph,
                segment,
                local_start,
                edit.old,
                edit.new,
                ids,
                author,
                when,
                edit.bold,
            )
            applied += 1
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
