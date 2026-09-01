"""Typer CLI wiring: every command reads an input .docx and writes to --out."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from lxml import etree

from . import comments as comments_mod
from . import validate as validate_mod
from . import word_verify as word_verify_mod
from .cleanup import AcceptedRevisions, accept_revisions, strip_format_revisions
from .errors import RedlineError
from .inspect import inspect_document
from .ooxml import IdAllocator, enable_tracking, next_change_id, utc_timestamp
from .package import DocxPackage
from .text_ops import (
    find_paragraph,
    insert_paragraph_after,
    replace_paragraph_text,
    replace_text,
)

app = typer.Typer(
    help="Safe, minimal Word (.docx) tracked-change editing.", no_args_is_help=True
)


def _document(package: DocxPackage) -> etree._Element:
    return package.xml("word/document.xml")


def _fail(message: str) -> None:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(1)


def _save(package: DocxPackage, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        package.save(out_path)
    except ValueError as error:
        _fail(str(error))


def _wordprocessingml_roots(
    package: DocxPackage,
) -> list[tuple[str, etree._Element]]:
    """Return revision-bearing Word story parts without loading unrelated XML."""
    roots: list[tuple[str, etree._Element]] = []
    story_parts = {
        "word/comments.xml",
        "word/document.xml",
        "word/endnotes.xml",
        "word/footnotes.xml",
    }
    for name in package.all_part_names():
        is_header_or_footer = name.startswith(("word/header", "word/footer"))
        if name not in story_parts and not is_header_or_footer:
            continue
        root = package.xml(name)
        if (
            etree.QName(root).namespace
            == "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        ):
            roots.append((name, root))
    return roots


def _prepare_edit(package: DocxPackage) -> tuple[etree._Element, IdAllocator, str]:
    document = _document(package)
    enable_tracking(package.xml("word/settings.xml"))
    return document, next_change_id(document), utc_timestamp()


@app.command()
def inspect(
    input_path: Path = typer.Argument(..., exists=True, readable=True),
    json_output: bool = typer.Option(
        False, "--json", help="Print machine-readable JSON."
    ),
) -> None:
    """Dump paragraphs with style, breaks, and revision-aware text."""
    package = DocxPackage(input_path)
    infos = inspect_document(_document(package))
    if json_output:
        typer.echo(
            json.dumps([info.__dict__ for info in infos], ensure_ascii=False, indent=2)
        )
        return
    for info in infos:
        typer.echo(
            f"P{info.index:03d} {info.location} style={info.style!r} "
            f"page_break={info.page_break} section_break={info.section_break} "
            f"ins={info.insertions} del={info.deletions} text={info.text!r}"
        )


@app.command("list-comments")
def list_comments_cmd(
    input_path: Path = typer.Argument(..., exists=True, readable=True),
) -> None:
    """List existing Word comments (id, author, date, text)."""
    package = DocxPackage(input_path)
    for comment in comments_mod.list_comments(package):
        typer.echo(
            f"#{comment.comment_id} [{comment.author} {comment.date}] {comment.text}"
        )


@app.command()
def replace(
    input_path: Path = typer.Argument(..., exists=True, readable=True),
    old: str = typer.Argument(..., help="Exact text to find."),
    new: str = typer.Argument(..., help="Replacement text."),
    out: Path = typer.Option(..., "--out"),
    author: str = typer.Option(
        ..., "--author", help="Reviewer identity written into Word revisions."
    ),
    occurrence: int | None = typer.Option(
        None, "--occurrence", help="Replace only the Nth match (0-based)."
    ),
    all_occurrences: bool = typer.Option(False, "--all", help="Replace every match."),
    bold: bool | None = typer.Option(
        None, "--bold/--no-bold", help="Force bold on/off for the inserted text."
    ),
    paragraph_contains: str | None = typer.Option(
        None,
        "--paragraph-contains",
        help="Only search paragraphs containing this text.",
    ),
) -> None:
    """Replace text as a minimal tracked change (w:ins/w:del).

    By default, exactly one match must exist in the whole document - this is a
    safety net against silently editing the wrong occurrence.
    """
    package = DocxPackage(input_path)
    document, ids, when = _prepare_edit(package)
    try:
        count = replace_text(
            document,
            old,
            new,
            ids,
            author,
            when,
            all_occurrences=all_occurrences,
            occurrence=occurrence,
            bold=bold,
            paragraph_contains=paragraph_contains,
        )
    except RedlineError as error:
        _fail(str(error))
        return
    _save(package, out)
    typer.echo(f"OK: {count} replacement(s) -> {out}")


@app.command("replace-batch")
def replace_batch(
    input_path: Path = typer.Argument(..., exists=True, readable=True),
    pairs_file: Path = typer.Option(
        ...,
        "--pairs",
        exists=True,
        readable=True,
        help="JSON array of replacement objects.",
    ),
    out: Path = typer.Option(..., "--out"),
    author: str = typer.Option(
        ..., "--author", help="Reviewer identity written into Word revisions."
    ),
) -> None:
    """Apply a sequential list of tracked replacements from a JSON file.

    Each array element is an object: {"old": "...", "new": "...", "all": false,
    "occurrence": null, "bold": null, "paragraph_contains": null}. Only "old" and
    "new" are required; this replaces the throwaway per-session Python scripts
    previously used to apply a batch of proofreading edits.
    """
    package = DocxPackage(input_path)
    document, ids, when = _prepare_edit(package)
    pairs = json.loads(pairs_file.read_text(encoding="utf-8"))
    total = 0
    for index, pair in enumerate(pairs):
        try:
            total += replace_text(
                document,
                pair["old"],
                pair["new"],
                ids,
                author,
                when,
                all_occurrences=pair.get("all", False),
                occurrence=pair.get("occurrence"),
                bold=pair.get("bold"),
                paragraph_contains=pair.get("paragraph_contains"),
            )
        except RedlineError as error:
            _fail(f"pair {index} ({pair.get('old')!r}): {error}")
    _save(package, out)
    typer.echo(f"OK: {total} replacement(s) from {len(pairs)} pair(s) -> {out}")


@app.command("replace-paragraph")
def replace_paragraph_cmd(
    input_path: Path = typer.Argument(..., exists=True, readable=True),
    text: str = typer.Option(..., "--text", help="New paragraph text."),
    out: Path = typer.Option(..., "--out"),
    match: str = typer.Option(
        ..., "--match", help="Text identifying the target paragraph."
    ),
    exact: bool = typer.Option(
        False, "--exact", help="Treat --match as an exact full-text match."
    ),
    author: str = typer.Option(
        ..., "--author", help="Reviewer identity written into Word revisions."
    ),
    bold: bool | None = typer.Option(None, "--bold/--no-bold"),
) -> None:
    """Replace an entire paragraph's text as a tracked delete+insert."""
    package = DocxPackage(input_path)
    document, ids, when = _prepare_edit(package)
    try:
        paragraph = find_paragraph(
            document, exact=match if exact else None, contains=None if exact else match
        )
        replace_paragraph_text(paragraph, text, ids, author, when, bold=bold)
    except RedlineError as error:
        _fail(str(error))
        return
    _save(package, out)
    typer.echo(f"OK: replaced paragraph -> {out}")


@app.command("insert-paragraph")
def insert_paragraph_cmd(
    input_path: Path = typer.Argument(..., exists=True, readable=True),
    text: str = typer.Option(..., "--text", help="Text of the new paragraph."),
    out: Path = typer.Option(..., "--out"),
    after: str = typer.Option(
        ..., "--after", help="Text identifying the anchor paragraph."
    ),
    exact: bool = typer.Option(
        False, "--exact", help="Treat --after as an exact full-text match."
    ),
    author: str = typer.Option(
        ..., "--author", help="Reviewer identity written into Word revisions."
    ),
    bold: bool | None = typer.Option(None, "--bold/--no-bold"),
) -> None:
    """Insert a new tracked paragraph right after an anchor paragraph."""
    package = DocxPackage(input_path)
    document, ids, when = _prepare_edit(package)
    try:
        anchor = find_paragraph(
            document, exact=after if exact else None, contains=None if exact else after
        )
        insert_paragraph_after(anchor, text, ids, author, when, bold=bold)
    except RedlineError as error:
        _fail(str(error))
        return
    _save(package, out)
    typer.echo(f"OK: inserted paragraph -> {out}")


@app.command("add-comment")
def add_comment_cmd(
    input_path: Path = typer.Argument(..., exists=True, readable=True),
    text: str = typer.Option(..., "--text", help="Comment body."),
    out: Path = typer.Option(..., "--out"),
    match: str = typer.Option(
        ..., "--match", help="Text identifying the target paragraph."
    ),
    exact: bool = typer.Option(
        False, "--exact", help="Treat --match as an exact full-text match."
    ),
    author: str = typer.Option(
        ..., "--author", help="Reviewer identity written into Word comments."
    ),
) -> None:
    """Anchor a Word comment to a paragraph, adding comments.xml plumbing if needed."""
    package = DocxPackage(input_path)
    document = _document(package)
    when = utc_timestamp()
    try:
        paragraph = find_paragraph(
            document, exact=match if exact else None, contains=None if exact else match
        )
        comment_id = comments_mod.add_comment(
            package, paragraph, text, author=author, when=when
        )
    except RedlineError as error:
        _fail(str(error))
        return
    _save(package, out)
    typer.echo(f"OK: added comment #{comment_id} -> {out}")


@app.command("strip-comments")
def strip_comments_cmd(
    input_path: Path = typer.Argument(..., exists=True, readable=True),
    out: Path = typer.Option(..., "--out"),
) -> None:
    """Remove all comments and their anchors from the document, headers, and footers."""
    package = DocxPackage(input_path)
    comments_mod.strip_comments(package)
    _save(package, out)
    typer.echo(f"OK: stripped comments -> {out}")


@app.command("strip-format-revisions")
def strip_format_revisions_cmd(
    input_path: Path = typer.Argument(..., exists=True, readable=True),
    out: Path = typer.Option(..., "--out"),
) -> None:
    """Remove formatting-only revision markers (w:pPrChange) that clutter the diff."""
    package = DocxPackage(input_path)
    removed = strip_format_revisions(_document(package))
    _save(package, out)
    typer.echo(f"OK: removed {removed} w:pPrChange node(s) -> {out}")


@app.command("accept-revisions")
def accept_revisions_cmd(
    input_path: Path = typer.Argument(..., exists=True, readable=True),
    out: Path = typer.Option(..., "--out"),
) -> None:
    """Accept all existing revisions into a separate review copy."""
    package = DocxPackage(input_path)
    accepted = AcceptedRevisions()
    parts = _wordprocessingml_roots(package)
    for _, document in parts:
        accepted.add(accept_revisions(document))
    _save(package, out)
    typer.echo(
        "OK: accepted "
        f"{accepted.insertions} insertion(s), {accepted.deletions} deletion(s), and "
        f"{accepted.property_changes} property change(s); removed "
        f"{accepted.empty_paragraphs} empty paragraph(s) across {len(parts)} "
        f"part(s) -> {out}"
    )


@app.command("enable-tracking")
def enable_tracking_cmd(
    input_path: Path = typer.Argument(..., exists=True, readable=True),
    out: Path = typer.Option(..., "--out"),
) -> None:
    """Turn on Track Changes (w:trackRevisions) for the document."""
    package = DocxPackage(input_path)
    enable_tracking(package.xml("word/settings.xml"))
    _save(package, out)
    typer.echo(f"OK: tracking enabled -> {out}")


@app.command()
def validate(
    input_path: Path = typer.Argument(..., exists=True, readable=True),
    original: Path | None = typer.Option(
        None,
        "--original",
        exists=True,
        readable=True,
        help="Pre-edit .docx to diff safety checks against.",
    ),
    require_changes: bool = typer.Option(
        True, "--require-changes/--no-require-changes"
    ),
    max_deletion_length: int | None = typer.Option(
        None,
        "--max-deletion-length",
        help="Flag any single tracked deletion longer than this.",
    ),
    number_pattern: str = typer.Option(
        r"[<>]?-?\d+(?:\.\d+)?%?",
        "--number-pattern",
        help="Regex for numbers that must survive unchanged.",
    ),
    contains: list[str] = typer.Option(
        [], "--contains", help="Fragment that must be present (repeatable)."
    ),
    not_contains: list[str] = typer.Option(
        [], "--not-contains", help="Fragment that must be absent (repeatable)."
    ),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Run safety checks on an edited .docx before delivering it."""
    report = validate_mod.ValidationReport()
    validate_mod.check_zip_integrity(input_path, report)
    package = DocxPackage(input_path)
    document = _document(package)
    validate_mod.check_tracking_enabled(package, report)
    validate_mod.check_has_changes(document, report, required=require_changes)
    validate_mod.check_no_formatting_insertions(document, report)
    validate_mod.check_comments_consistent(package, document, report)
    if max_deletion_length is not None:
        validate_mod.check_max_deletion_length(document, report, max_deletion_length)
    if original is not None:
        original_document = DocxPackage(original).xml("word/document.xml")
        validate_mod.check_paragraph_count(document, original_document, report)
        validate_mod.check_protect_numbers(
            document, original_document, number_pattern, report
        )
        validate_mod.check_run_properties_preserved(document, original_document, report)
    if contains:
        validate_mod.check_contains(document, contains, report)
    if not_contains:
        validate_mod.check_not_contains(document, not_contains, report)

    if json_output:
        typer.echo(
            json.dumps(
                [check.__dict__ for check in report.checks],
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        for check in report.checks:
            status = "PASS" if check.passed else "FAIL"
            typer.echo(f"[{status}] {check.name}: {check.detail}")
    if not report.ok:
        raise typer.Exit(1)


@app.command("verify-word")
def verify_word_cmd(
    input_path: Path = typer.Argument(..., exists=True, readable=True),
    pdf: Path = typer.Option(
        ..., "--pdf", help="Where to write the Word-rendered verification PDF."
    ),
    png_dir: Path | None = typer.Option(
        None,
        "--png-dir",
        help="Rasterize each PDF page into this directory (requires pdftoppm).",
    ),
    required_font: list[str] = typer.Option(
        [],
        "--required-font",
        help="Font that must be declared somewhere in the document (repeatable).",
    ),
    expected_font: list[str] = typer.Option(
        [],
        "--expected-font",
        help=(
            "Restrict declared fonts to this set; any other declared font is "
            "flagged (repeatable)."
        ),
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Print machine-readable JSON."
    ),
) -> None:
    """Verify layout/pagination via Microsoft Word (macOS only) and audit fonts.

    Opens `input_path` read-only through Microsoft Word automation,
    repaginates it, and exports a verification PDF - the input file is never
    modified. LibreOffice is deliberately not used as a fallback: it is not
    an authoritative renderer for Word tracked changes and can show
    different layout/pagination than Microsoft Word.

    Declared fonts (from word/styles.xml and word/document.xml) are
    complementary to the rendered PDF: a declaration alone can't prove Word
    didn't substitute an unavailable font.
    """
    package = DocxPackage(input_path)
    try:
        result = word_verify_mod.verify_word(
            input_path,
            pdf,
            package=package,
            png_dir=png_dir,
            required_fonts=required_font,
            expected_fonts=expected_font,
        )
    except RedlineError as error:
        _fail(str(error))
        return
    if json_output:
        typer.echo(json.dumps(result.__dict__, ensure_ascii=False, indent=2))
    else:
        typer.echo(
            f"Word {result.word_version}: {result.page_count} page(s) -> "
            f"{result.pdf_path}"
        )
        if result.png_paths:
            typer.echo(f"PNG(s): {len(result.png_paths)} page(s) -> {png_dir}")
        typer.echo(f"declared fonts: {', '.join(result.declared_fonts) or '(none)'}")
        if result.missing_required_fonts:
            typer.echo(f"MISSING required font(s): {result.missing_required_fonts}")
        if result.unexpected_fonts:
            typer.echo(f"UNEXPECTED font(s): {result.unexpected_fonts}")
    if not result.ok:
        raise typer.Exit(1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
