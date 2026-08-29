from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from docx_redline import comments as comments_mod
from docx_redline.cli import app
from docx_redline.ooxml import NSMAP
from docx_redline.package import DocxPackage
from docx_redline.text_ops import visible_text

runner = CliRunner()


def test_replace_command_writes_tracked_change(docx_factory, tmp_path: Path) -> None:
    docx = docx_factory("doc.docx", [["Hello world."]])
    out = tmp_path / "out.docx"

    result = runner.invoke(
        app,
        [
            "replace",
            str(docx),
            "world",
            "there",
            "--out",
            str(out),
            "--author",
            "Test Agent",
        ],
    )

    assert result.exit_code == 0, result.output
    package = DocxPackage(out)
    document = package.xml("word/document.xml")
    paragraph = document.xpath(
        ".//w:p",
        namespaces={
            "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        },
    )[0]
    assert visible_text(paragraph) == "Hello there."


def test_author_is_required_for_revisions_and_comments(
    docx_factory, tmp_path: Path
) -> None:
    docx = docx_factory("doc.docx", [["Hello world."]])
    revised = tmp_path / "revised.docx"

    result = runner.invoke(
        app, ["replace", str(docx), "world", "there", "--out", str(revised)]
    )

    assert result.exit_code == 2

    result = runner.invoke(
        app,
        [
            "replace",
            str(docx),
            "world",
            "there",
            "--out",
            str(revised),
            "--author",
            "Test Agent",
        ],
    )

    assert result.exit_code == 0, result.output
    document = DocxPackage(revised).xml("word/document.xml")
    authors = document.xpath(
        ".//w:ins/@w:author | .//w:del/@w:author", namespaces=NSMAP
    )
    assert authors == ["Test Agent", "Test Agent"]

    commented = tmp_path / "commented.docx"
    result = runner.invoke(
        app,
        [
            "add-comment",
            str(docx),
            "--match",
            "Hello world.",
            "--text",
            "Review this.",
            "--out",
            str(commented),
            "--author",
            "Test Agent",
        ],
    )

    assert result.exit_code == 0, result.output
    comments = comments_mod.list_comments(DocxPackage(commented))
    assert [comment.author for comment in comments] == ["Test Agent"]


def test_replace_command_reports_ambiguous_match(docx_factory, tmp_path: Path) -> None:
    docx = docx_factory("doc.docx", [["a b a"]])
    out = tmp_path / "out.docx"

    result = runner.invoke(
        app,
        [
            "replace",
            str(docx),
            "a",
            "c",
            "--out",
            str(out),
            "--author",
            "Test Agent",
        ],
    )

    assert result.exit_code == 1
    assert "expected exactly one match" in result.output
    assert not out.exists()


def test_replace_batch_command_applies_all_pairs(docx_factory, tmp_path: Path) -> None:
    docx = docx_factory("doc.docx", [["one two three"]])
    pairs_file = tmp_path / "pairs.json"
    pairs_file.write_text('[{"old": "one", "new": "1"}, {"old": "two", "new": "2"}]')
    out = tmp_path / "out.docx"

    result = runner.invoke(
        app,
        [
            "replace-batch",
            str(docx),
            "--pairs",
            str(pairs_file),
            "--out",
            str(out),
            "--author",
            "Test Agent",
        ],
    )

    assert result.exit_code == 0, result.output
    package = DocxPackage(out)
    document = package.xml("word/document.xml")
    paragraph = document.xpath(
        ".//w:p",
        namespaces={
            "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        },
    )[0]
    assert visible_text(paragraph) == "1 2 three"


def test_validate_command_fails_without_changes(docx_factory) -> None:
    docx = docx_factory("doc.docx", [["Untouched text."]])

    result = runner.invoke(app, ["validate", str(docx)])

    assert result.exit_code == 1
    assert "FAIL" in result.output


def test_inspect_command_prints_paragraphs(docx_factory) -> None:
    docx = docx_factory("doc.docx", [["Hello there."]])

    result = runner.invoke(app, ["inspect", str(docx)])

    assert result.exit_code == 0
    assert "Hello there." in result.output
