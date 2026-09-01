"""Composable safety checks to run on an edited .docx before delivery."""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from lxml import etree

from .comments import list_comments
from .ooxml import NSMAP, RprSignature, rpr_signature, w
from .package import DocxPackage


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


@dataclass
class ValidationReport:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(check.passed for check in self.checks)

    def add(self, name: str, passed: bool, detail: str) -> None:
        self.checks.append(CheckResult(name, passed, detail))


def _visible_text(paragraph: etree._Element) -> str:
    return "".join(paragraph.xpath(".//w:t/text()", namespaces=NSMAP))


def _body_paragraphs(document: etree._Element) -> list[etree._Element]:
    """All paragraphs in document order, including ones nested in tables.

    Uses `.//w:p` rather than direct children so table-cell paragraphs are
    covered too, matching the scope `replace_text` already searches.
    """
    body = document.find("w:body", namespaces=NSMAP)
    if body is None:
        raise ValueError("word/document.xml has no w:body")
    return cast("list[etree._Element]", body.xpath(".//w:p", namespaces=NSMAP))


def check_zip_integrity(path: Path, report: ValidationReport) -> None:
    with zipfile.ZipFile(path) as archive:
        bad_entry = archive.testzip()
    report.add(
        "zip-integrity", bad_entry is None, bad_entry or "archive is well-formed"
    )


def check_tracking_enabled(package: DocxPackage, report: ValidationReport) -> None:
    settings = package.xml("word/settings.xml")
    enabled = settings.find("w:trackRevisions", namespaces=NSMAP) is not None
    report.add(
        "tracking-enabled",
        enabled,
        "w:trackRevisions present" if enabled else "missing w:trackRevisions",
    )


def check_has_changes(
    document: etree._Element, report: ValidationReport, *, required: bool
) -> None:
    insertions = document.xpath(".//w:ins", namespaces=NSMAP)
    deletions = document.xpath(".//w:del", namespaces=NSMAP)
    passed = bool(insertions or deletions) if required else True
    report.add(
        "has-changes",
        passed,
        f"insertions={len(insertions)} deletions={len(deletions)}",
    )


_INSERTION_FORMATTING_TAGS = (
    "b",
    "bCs",
    "i",
    "iCs",
    "u",
    "strike",
    "dstrike",
    "vertAlign",
    "rStyle",
)


def _preceding_deletion_signature(ins: etree._Element) -> RprSignature | None:
    """The rpr signature of a `w:del` immediately preceding this `w:ins`, if any.

    `replace_text`/`apply_replace_batch`/`replace_paragraph_text` always place
    a replacement's deletion as the tracked insertion's immediately preceding
    sibling when both exist (see `text_ops._apply_replacement` and
    `replace_paragraph_text`), so this is the "source formatting" an
    insertion is judged against. Returns `None` - no source to compare, so
    the caller falls back to always flagging - when there's no preceding
    deletion at all (e.g. `insert-paragraph`, genuinely new content) or the
    deletion spans runs with more than one formatting signature (should not
    happen via this tool's own commands, which refuse such a replacement
    outright, but a hand-edited or foreign document could still produce one).
    """
    previous = ins.getprevious()
    if previous is None or previous.tag != w("del"):
        return None
    signatures = {
        rpr_signature(run.find("w:rPr", namespaces=NSMAP))
        for run in previous.xpath(".//w:r", namespaces=NSMAP)
    }
    if len(signatures) != 1:
        return None
    return next(iter(signatures))


def check_no_formatting_insertions(
    document: etree._Element, report: ValidationReport
) -> None:
    """Flag inserted text carrying newly introduced notable run formatting.

    Covers bold, italic, underline, strike, subscript/superscript (vertAlign),
    and character style (rStyle). An insertion whose run properties exactly
    match the formatting of the `w:del` it immediately replaces is a
    formatting-*preserving* edit - required to keep the document's
    established formatting - and passes; this check exists to catch
    formatting a replacement introduces that the source text didn't have
    (e.g. an explicit --bold override, or a bug), not to flag every
    replacement that happens to inherit its source run's own formatting.
    Font, size, and color are intentionally excluded: replacements routinely
    carry those over from the source run (e.g. CJK font hints) and flagging
    every such insertion would make the check useless in practice.
    """
    offenders: list[tuple[etree._Element, tuple[str, ...]]] = []
    preserved = 0
    for ins in document.xpath(".//w:ins", namespaces=NSMAP):
        source_signature = _preceding_deletion_signature(ins)
        for run in ins.xpath(".//w:r", namespaces=NSMAP):
            rpr = run.find("w:rPr", namespaces=NSMAP)
            if rpr is None:
                continue
            tags = tuple(
                sorted(
                    {
                        etree.QName(child).localname
                        for child in rpr
                        if etree.QName(child).localname in _INSERTION_FORMATTING_TAGS
                    }
                )
            )
            if not tags:
                continue
            if source_signature is not None and rpr_signature(rpr) == source_signature:
                preserved += 1
                continue
            offenders.append((run, tags))
    if offenders:
        tag_names = sorted({tag for _, tags in offenders for tag in tags})
        detail = (
            "newly introduced formatting inside w:ins: "
            + ", ".join(tag_names)
            + f" ({len(offenders)} run(s))"
        )
    else:
        detail = "no inserted text carries newly introduced formatting"
        if preserved:
            detail += (
                f" ({preserved} run(s) preserve formatting from the replaced text)"
            )
    report.add("no-formatting-insertions", not offenders, detail)


def _original_equivalent_signal(
    paragraph: etree._Element,
) -> list[tuple[str, RprSignature | None]]:
    """Rebuild this paragraph's original text, in original order.

    Walks `w:delText` (deleted - originally there) and `w:t` outside any
    `w:ins` (untouched - still there) in document order; either kind of node
    is, by construction, a verbatim copy of some contiguous original span.
    `w:t` inside `w:ins` is skipped - inserted text has no original
    counterpart. The formatting signature is `None` for deleted characters
    (position placeholder only, not checked) and the current signature for
    untouched ones (what this check actually verifies).
    """
    signal: list[tuple[str, RprSignature | None]] = []
    for node in paragraph.iter(w("t"), w("delText")):
        is_insertion = node.tag == w("t") and node.xpath(
            "ancestor::w:ins", namespaces=NSMAP
        )
        if is_insertion:
            continue
        run = node.getparent()
        rpr = run.find("w:rPr", namespaces=NSMAP) if run is not None else None
        signature = rpr_signature(rpr) if node.tag == w("t") else None
        signal.extend((ch, signature) for ch in node.text or "")
    return signal


def check_run_properties_preserved(
    document: etree._Element, original: etree._Element, report: ValidationReport
) -> None:
    """Text left untouched by tracked changes must keep its original formatting.

    Reconstructs each paragraph's original text from the current document (its
    deletions plus whatever wasn't inserted or deleted) and walks it alongside
    the real original paragraph position by position - this is an exact
    reconstruction, not a fuzzy alignment, so repeated characters/phrases with
    different original formatting can't be matched to the wrong occurrence. A
    paragraph is skipped entirely (no false failure risked) when the
    reconstructed text doesn't match the original verbatim - e.g. a
    whole-paragraph replacement leaves nothing to reconstruct, and a paragraph
    inserted or removed elsewhere in the document desyncs the by-index pairing.
    """
    problems: list[str] = []
    for index, (current_p, original_p) in enumerate(
        zip(_body_paragraphs(document), _body_paragraphs(original), strict=False)
    ):
        reconstructed = _original_equivalent_signal(current_p)
        baseline = _original_equivalent_signal(original_p)
        if [ch for ch, _ in reconstructed] != [ch for ch, _ in baseline]:
            continue
        for (char, baseline_sig), (_, current_sig) in zip(
            baseline, reconstructed, strict=True
        ):
            if current_sig is None:  # deleted - not what this check verifies
                continue
            if baseline_sig != current_sig:
                problems.append(
                    f"paragraph {index}: formatting changed on unedited text {char!r}"
                )
    detail = (
        "untouched text keeps its original formatting"
        if not problems
        else f"{len(problems)} formatting change(s) on unedited text: "
        + "; ".join(problems[:5])
    )
    report.add("run-properties-preserved", not problems, detail)


def check_max_deletion_length(
    document: etree._Element, report: ValidationReport, limit: int
) -> None:
    deletions = document.xpath(".//w:del", namespaces=NSMAP)
    lengths = [
        len("".join(node.xpath(".//w:delText/text()", namespaces=NSMAP)))
        for node in deletions
    ]
    longest = max(lengths, default=0)
    report.add(
        "max-deletion-length",
        longest <= limit,
        f"longest deletion is {longest} chars (limit {limit})",
    )


def check_comments_consistent(
    package: DocxPackage, document: etree._Element, report: ValidationReport
) -> None:
    comments = list_comments(package)
    problems: list[str] = []
    for comment in comments:
        for anchor in ("commentRangeStart", "commentRangeEnd", "commentReference"):
            matches = document.xpath(
                f".//w:{anchor}[@w:id=$id]",
                namespaces=NSMAP,
                id=str(comment.comment_id),
            )
            if len(matches) != 1:
                problems.append(
                    f"comment {comment.comment_id}: {len(matches)} {anchor} anchor(s)"
                )
    detail = (
        "; ".join(problems)
        if problems
        else f"{len(comments)} comment(s) all anchored correctly"
    )
    report.add("comments-consistent", not problems, detail)


def check_paragraph_count(
    document: etree._Element, original: etree._Element, report: ValidationReport
) -> None:
    current, baseline = len(_body_paragraphs(document)), len(_body_paragraphs(original))
    report.add(
        "paragraph-count",
        current == baseline,
        f"{current} paragraph(s), expected {baseline}",
    )


def check_protect_numbers(
    document: etree._Element,
    original: etree._Element,
    pattern: str,
    report: ValidationReport,
) -> None:
    regex = re.compile(pattern)
    current_text = "\n".join(_visible_text(p) for p in _body_paragraphs(document))
    original_text = "\n".join(_visible_text(p) for p in _body_paragraphs(original))
    current_numbers, original_numbers = (
        regex.findall(current_text),
        regex.findall(original_text),
    )
    report.add(
        "protect-numbers",
        current_numbers == original_numbers,
        f"found {len(current_numbers)}, expected {len(original_numbers)} unchanged",
    )


def check_contains(
    document: etree._Element, fragments: list[str], report: ValidationReport
) -> None:
    text = "\n".join(_visible_text(p) for p in _body_paragraphs(document))
    missing = [fragment for fragment in fragments if fragment not in text]
    detail = "all expected fragments present" if not missing else f"missing: {missing}"
    report.add("contains", not missing, detail)


def check_not_contains(
    document: etree._Element, fragments: list[str], report: ValidationReport
) -> None:
    text = "\n".join(_visible_text(p) for p in _body_paragraphs(document))
    present = [fragment for fragment in fragments if fragment in text]
    detail = "no forbidden fragment present" if not present else f"present: {present}"
    report.add("not-contains", not present, detail)
