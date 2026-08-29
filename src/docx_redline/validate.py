"""Composable safety checks to run on an edited .docx before delivery."""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from lxml import etree

from .comments import list_comments
from .ooxml import NSMAP
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


def check_no_bold_insertions(
    document: etree._Element, report: ValidationReport
) -> None:
    offenders = document.xpath(".//w:ins//w:b | .//w:ins//w:bCs", namespaces=NSMAP)
    detail = (
        "no inserted text is bold"
        if not offenders
        else f"{len(offenders)} bold run(s) inside w:ins"
    )
    report.add("no-bold-insertions", not offenders, detail)


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
