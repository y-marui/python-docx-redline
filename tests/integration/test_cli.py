from __future__ import annotations

import json
from pathlib import Path

from lxml import etree
from typer.testing import CliRunner

from docx_redline import cli as cli_mod
from docx_redline import comments as comments_mod
from docx_redline.cli import app
from docx_redline.errors import RedlineError
from docx_redline.ooxml import NSMAP
from docx_redline.package import DocxPackage
from docx_redline.text_ops import visible_text
from docx_redline.word_verify import WordVerifyResult

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


def test_replace_command_diffs_full_sentence_to_minimal_span_by_default(
    docx_factory, tmp_path: Path
) -> None:
    docx = docx_factory("doc.docx", [["猫を見た。"]])
    out = tmp_path / "out.docx"

    result = runner.invoke(
        app,
        [
            "replace",
            str(docx),
            "猫を見た。",
            "猫が見た。",
            "--out",
            str(out),
            "--author",
            "Test Agent",
        ],
    )

    assert result.exit_code == 0, result.output
    document = DocxPackage(out).xml("word/document.xml")
    deleted = "".join(document.xpath(".//w:delText/text()", namespaces=NSMAP))
    assert deleted == "を"


def test_replace_command_before_after_disambiguate_repeated_match(
    docx_factory, tmp_path: Path
) -> None:
    docx = docx_factory("doc.docx", [["猫を見た。犬を見た。"]])
    out = tmp_path / "out.docx"

    result = runner.invoke(
        app,
        [
            "replace",
            str(docx),
            "を",
            "が",
            "--out",
            str(out),
            "--author",
            "Test Agent",
            "--before",
            "犬",
            "--after",
            "見",
        ],
    )

    assert result.exit_code == 0, result.output
    document = DocxPackage(out).xml("word/document.xml")
    paragraph = document.xpath(".//w:p", namespaces=NSMAP)[0]
    assert visible_text(paragraph) == "猫を見た。犬が見た。"


def test_replace_batch_command_rejects_overlapping_pairs(
    docx_factory, tmp_path: Path
) -> None:
    docx = docx_factory("doc.docx", [["Hello world."]])
    pairs_file = tmp_path / "pairs.json"
    pairs_file.write_text(
        '[{"old": "Hello wo", "new": "HELLO WO"}, '
        '{"old": "lo world", "new": "LO WORLD"}]'
    )
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

    assert result.exit_code == 1
    assert "overlapping" in result.output
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


def test_verify_word_command_reports_ok_result_as_json(
    monkeypatch, docx_factory, tmp_path: Path
) -> None:
    docx = docx_factory("doc.docx", [["Plain text."]])
    pdf = tmp_path / "out.pdf"

    def fake_verify_word(input_path, pdf_path, **kwargs):
        return WordVerifyResult(
            word_version="16.78",
            page_count=2,
            pdf_path=str(pdf_path),
            pdf_sha256="deadbeef",
            declared_fonts=["Arial"],
        )

    monkeypatch.setattr(cli_mod.word_verify_mod, "verify_word", fake_verify_word)

    result = runner.invoke(app, ["verify-word", str(docx), "--pdf", str(pdf), "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["word_version"] == "16.78"
    assert payload["page_count"] == 2


def test_verify_word_command_exits_nonzero_on_missing_required_font(
    monkeypatch, docx_factory, tmp_path: Path
) -> None:
    docx = docx_factory("doc.docx", [["Plain text."]])
    pdf = tmp_path / "out.pdf"

    def fake_verify_word(input_path, pdf_path, **kwargs):
        return WordVerifyResult(
            word_version="16.78",
            page_count=1,
            pdf_path=str(pdf_path),
            pdf_sha256="deadbeef",
            missing_required_fonts=["Times New Roman"],
        )

    monkeypatch.setattr(cli_mod.word_verify_mod, "verify_word", fake_verify_word)

    result = runner.invoke(
        app,
        [
            "verify-word",
            str(docx),
            "--pdf",
            str(pdf),
            "--required-font",
            "Times New Roman",
        ],
    )

    assert result.exit_code == 1
    assert "MISSING required font(s)" in result.output


def test_verify_word_command_reports_platform_error(
    monkeypatch, docx_factory, tmp_path: Path
) -> None:
    docx = docx_factory("doc.docx", [["Plain text."]])
    pdf = tmp_path / "out.pdf"

    def fake_verify_word(input_path, pdf_path, **kwargs):
        raise RedlineError("verify-word requires macOS with Microsoft Word installed")

    monkeypatch.setattr(cli_mod.word_verify_mod, "verify_word", fake_verify_word)

    result = runner.invoke(app, ["verify-word", str(docx), "--pdf", str(pdf)])

    assert result.exit_code == 1
    assert "requires macOS" in result.output


def test_accept_revisions_command_processes_non_body_wordprocessingml_parts(
    docx_factory, tmp_path: Path
) -> None:
    docx = docx_factory("doc.docx", [["Body text."]])
    package = DocxPackage(docx)
    body = package.xml("word/document.xml")
    body_paragraph = body.xpath(".//w:p", namespaces=NSMAP)[0]
    body_run = body_paragraph.xpath("./w:r", namespaces=NSMAP)[0]
    body_insertion = etree.Element(
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}ins"
    )
    body_insertion.append(body_run)
    body_paragraph.insert(0, body_insertion)
    header = etree.fromstring(
        b'<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        b'<w:p><w:del w:id="1"><w:r><w:delText>Old header.</w:delText></w:r></w:del>'
        b"</w:p></w:hdr>"
    )
    package.new_xml("word/header1.xml", header)
    source = tmp_path / "source.docx"
    package.save(source)
    source_settings = DocxPackage(source).raw("word/settings.xml")
    out = tmp_path / "accepted.docx"

    result = runner.invoke(app, ["accept-revisions", str(source), "--out", str(out)])

    assert result.exit_code == 0, result.output
    assert "1 insertion(s), 1 deletion(s)" in result.output
    assert source.read_bytes() != out.read_bytes()
    accepted = DocxPackage(out)
    assert not accepted.xml("word/document.xml").xpath(".//w:ins", namespaces=NSMAP)
    assert not accepted.xml("word/header1.xml").xpath(".//w:del", namespaces=NSMAP)
    assert accepted.xml("word/header1.xml").xpath(".//w:p", namespaces=NSMAP) == []
    assert accepted.raw("word/settings.xml") == source_settings
