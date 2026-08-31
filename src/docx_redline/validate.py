"""Composable safety checks to run on an edited .docx before delivery."""

from __future__ import annotations

import difflib
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from lxml import etree

from .comments import list_comments
from .ooxml import NSMAP, RprSignature, rpr_signature
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
    body = document.find("w:body", namespaces=NSMAP)
    if body is None:
        raise ValueError("word/document.xml has no w:body")
    return cast("list[etree._Element]", body.findall("w:p", namespaces=NSMAP))


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


def check_no_formatting_insertions(
    document: etree._Element, report: ValidationReport
) -> None:
    """Flag any inserted text carrying notable run formatting for manual review.

    Covers bold, italic, underline, strike, subscript/superscript (vertAlign),
    and character style (rStyle) - always, whether it came from an explicit
    --bold-style override or was preserved from the replaced text. This is a
    conservative pre-delivery check, not an attempt to guess intent. Font,
    size, and color are intentionally excluded: replacements routinely carry
    those over from the source run (e.g. CJK font hints) and flagging every
    such insertion would make the check useless in practice.
    """
    offenders: list[tuple[str, etree._Element]] = []
    for tag in _INSERTION_FORMATTING_TAGS:
        offenders.extend(
            (tag, node)
            for node in document.xpath(f".//w:ins//w:{tag}", namespaces=NSMAP)
        )
    detail = (
        "no inserted text carries notable formatting"
        if not offenders
        else "formatting inside w:ins: "
        + ", ".join(sorted({tag for tag, _ in offenders}))
        + f" ({len(offenders)} run(s))"
    )
    report.add("no-formatting-insertions", not offenders, detail)


def _untouched_signal(paragraph: etree._Element) -> list[tuple[str, RprSignature]]:
    """(char, formatting signature) for text outside w:ins, in document order."""
    signal: list[tuple[str, RprSignature]] = []
    for text_node in paragraph.xpath(".//w:t", namespaces=NSMAP):
        if text_node.xpath("ancestor::w:ins", namespaces=NSMAP):
            continue
        run = text_node.getparent()
        rpr = run.find("w:rPr", namespaces=NSMAP) if run is not None else None
        signature = rpr_signature(rpr)
        signal.extend((ch, signature) for ch in text_node.text or "")
    return signal


def check_run_properties_preserved(
    document: etree._Element, original: etree._Element, report: ValidationReport
) -> None:
    """Text left untouched by tracked changes must keep its original formatting.

    Compares, paragraph by paragraph, the formatting of surviving (non-inserted)
    text against the same text in `original`. Only text the alignment can place
    in an unbroken, unambiguous match is checked - anything else is skipped
    rather than risking a false failure (e.g. a whole-paragraph replacement
    leaves nothing untouched to compare, and is silently skipped).
    """
    problems: list[str] = []
    for index, (current_p, original_p) in enumerate(
        zip(_body_paragraphs(document), _body_paragraphs(original), strict=False)
    ):
        current_signal = _untouched_signal(current_p)
        original_signal = _untouched_signal(original_p)
        matcher = difflib.SequenceMatcher(
            None,
            [ch for ch, _ in original_signal],
            [ch for ch, _ in current_signal],
            autojunk=False,
        )
        for tag, i1, i2, j1, _ in matcher.get_opcodes():
            if tag != "equal":
                continue
            for offset in range(i2 - i1):
                orig_char, orig_sig = original_signal[i1 + offset]
                _, cur_sig = current_signal[j1 + offset]
                if orig_sig != cur_sig:
                    problems.append(
                        f"paragraph {index}: formatting changed on "
                        f"unedited text {orig_char!r}"
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
