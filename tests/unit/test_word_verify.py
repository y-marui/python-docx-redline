"""word_verify.py: command construction and error handling, without needing
macOS or Microsoft Word (see docx-redline#10's acceptance criteria)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest
from lxml import etree

from docx_redline.errors import RedlineError
from docx_redline.package import DocxPackage
from docx_redline.word_verify import (
    _applescript,
    _check_platform,
    _check_word_available,
    _rasterize_pdf,
    _run_applescript,
    audit_declared_fonts,
    verify_word,
)

_W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


@dataclass
class _FakeResult:
    """Duck-types the parts of subprocess.CompletedProcess this module reads."""

    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass
class _FakeRunner:
    """Records every command it was asked to run and replays canned results."""

    results: list[_FakeResult] = field(default_factory=list)
    calls: list[list[str]] = field(default_factory=list)

    def __call__(self, args: list[str]) -> _FakeResult:
        self.calls.append(args)
        return self.results[len(self.calls) - 1]


# --- audit_declared_fonts (pure, no subprocess) ------------------------------


def _add_styles_with_font(package: DocxPackage, font: str) -> None:
    styles = etree.fromstring(
        f"<w:styles {_W}><w:docDefaults><w:rPrDefault><w:rPr>"
        f'<w:rFonts w:ascii="{font}" w:hAnsi="{font}"/>'
        f"</w:rPr></w:rPrDefault></w:docDefaults></w:styles>".encode()
    )
    package.new_xml("word/styles.xml", styles)


def test_audit_declared_fonts_covers_styles_and_document(docx_factory) -> None:
    docx = docx_factory("doc.docx", [[("Body text", '<w:rFonts w:ascii="Arial"/>')]])
    package = DocxPackage(docx)
    _add_styles_with_font(package, "Times New Roman")

    fonts = audit_declared_fonts(package)

    assert fonts == {"Arial", "Times New Roman"}


def test_audit_declared_fonts_empty_when_none_declared(docx_factory) -> None:
    docx = docx_factory("doc.docx", [["Plain text."]])
    package = DocxPackage(docx)

    assert audit_declared_fonts(package) == set()


def _add_theme(package: DocxPackage, *, minor_latin: str, major_latin: str) -> None:
    theme = etree.fromstring(
        b'<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        b"<a:themeElements><a:fontScheme>"
        b'<a:majorFont><a:latin typeface="'
        + major_latin.encode()
        + b'"/></a:majorFont>'
        b'<a:minorFont><a:latin typeface="'
        + minor_latin.encode()
        + b'"/></a:minorFont>'
        b"</a:fontScheme></a:themeElements></a:theme>"
    )
    package.new_xml("word/theme/theme1.xml", theme)


def test_audit_declared_fonts_resolves_theme_referenced_fonts(docx_factory) -> None:
    # docDefaults commonly reference a font via asciiTheme/hAnsiTheme rather
    # than naming a typeface directly - this is how most real Word documents
    # declare their body font.
    docx = docx_factory("doc.docx", [["Plain text."]])
    package = DocxPackage(docx)
    styles = etree.fromstring(
        f"<w:styles {_W}><w:docDefaults><w:rPrDefault><w:rPr>"
        f'<w:rFonts w:asciiTheme="minorHAnsi" w:hAnsiTheme="minorHAnsi"/>'
        f"</w:rPr></w:rPrDefault></w:docDefaults></w:styles>".encode()
    )
    package.new_xml("word/styles.xml", styles)
    _add_theme(package, minor_latin="Calibri", major_latin="Calibri Light")

    fonts = audit_declared_fonts(package)

    assert fonts == {"Calibri"}


def test_audit_declared_fonts_keeps_unresolvable_theme_slot_name(
    docx_factory,
) -> None:
    # No theme part exists to resolve "minorHAnsi" against - the raw slot
    # name is kept rather than the declaration being silently dropped.
    docx = docx_factory(
        "doc.docx", [[("Body", '<w:rFonts w:asciiTheme="minorHAnsi"/>')]]
    )
    package = DocxPackage(docx)

    assert audit_declared_fonts(package) == {"minorHAnsi"}


# --- platform / Word availability checks -------------------------------------


def test_check_platform_raises_off_macos(monkeypatch) -> None:
    monkeypatch.setattr("docx_redline.word_verify.platform.system", lambda: "Linux")
    with pytest.raises(RedlineError, match="macOS"):
        _check_platform()


def test_check_platform_passes_on_macos(monkeypatch) -> None:
    monkeypatch.setattr("docx_redline.word_verify.platform.system", lambda: "Darwin")
    _check_platform()  # must not raise


def test_check_word_available_raises_when_osascript_fails() -> None:
    runner = _FakeRunner(results=[_FakeResult(returncode=1, stderr="not found")])
    with pytest.raises(RedlineError, match="not available"):
        _check_word_available(runner)
    assert runner.calls == [["osascript", "-e", 'id of application "Microsoft Word"']]


def test_check_word_available_passes_when_osascript_succeeds() -> None:
    runner = _FakeRunner(
        results=[_FakeResult(returncode=0, stdout="com.microsoft.Word")]
    )
    _check_word_available(runner)  # must not raise


# --- AppleScript construction and output parsing -----------------------------


def test_applescript_takes_paths_as_argv_not_source_text() -> None:
    # Paths must never be interpolated into the script source - a path
    # containing a quote could otherwise corrupt or inject into the script.
    script = _applescript()
    assert "/tmp/in.docx" not in script
    assert "item 1 of argv" in script
    assert "item 2 of argv" in script
    assert "open file name inputPath with read only" in script
    assert "format PDF" in script
    assert "close theDoc saving no" in script


def test_run_applescript_passes_paths_as_osascript_arguments() -> None:
    runner = _FakeRunner(results=[_FakeResult(returncode=0, stdout="16.78|3\n")])
    quoted_path = Path('/tmp/a "quoted" file.docx')
    _run_applescript(quoted_path, Path("out.pdf"), runner)
    args = runner.calls[0]
    assert args[0] == "osascript"
    assert args[-2:] == [str(quoted_path), "out.pdf"]
    # The path text itself is not embedded in the script argument.
    assert str(quoted_path) not in args[2]


def test_run_applescript_parses_version_and_page_count() -> None:
    runner = _FakeRunner(results=[_FakeResult(returncode=0, stdout="16.78|3\n")])
    version, pages = _run_applescript(Path("in.docx"), Path("out.pdf"), runner)
    assert version == "16.78"
    assert pages == 3


def test_run_applescript_raises_on_nonzero_exit() -> None:
    runner = _FakeRunner(
        results=[_FakeResult(returncode=1, stderr="document is damaged")]
    )
    with pytest.raises(RedlineError, match="export failed"):
        _run_applescript(Path("in.docx"), Path("out.pdf"), runner)


def test_run_applescript_raises_on_unparseable_output() -> None:
    runner = _FakeRunner(results=[_FakeResult(returncode=0, stdout="garbage")])
    with pytest.raises(RedlineError, match="could not parse"):
        _run_applescript(Path("in.docx"), Path("out.pdf"), runner)


# --- PNG rasterization --------------------------------------------------------


def test_rasterize_pdf_raises_when_pdftoppm_missing(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("docx_redline.word_verify.shutil.which", lambda name: None)
    runner = _FakeRunner()
    with pytest.raises(RedlineError, match="pdftoppm"):
        _rasterize_pdf(tmp_path / "in.pdf", tmp_path / "png", runner)


def test_rasterize_pdf_returns_sorted_generated_pages(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "docx_redline.word_verify.shutil.which", lambda name: "/usr/local/bin/pdftoppm"
    )
    png_dir = tmp_path / "png"

    def fake_run(args: list[str]) -> _FakeResult:
        png_dir.mkdir(parents=True, exist_ok=True)
        (png_dir / "page-2.png").write_bytes(b"")
        (png_dir / "page-1.png").write_bytes(b"")
        return _FakeResult(returncode=0)

    paths = _rasterize_pdf(tmp_path / "in.pdf", png_dir, fake_run)
    assert paths == [str(png_dir / "page-1.png"), str(png_dir / "page-2.png")]


def test_rasterize_pdf_removes_stale_pages_from_a_previous_larger_run(
    monkeypatch, tmp_path: Path
) -> None:
    # A previous run with more pages left page-3.png/page-4.png behind; a
    # new, shorter PDF's run must not report them as current output.
    monkeypatch.setattr(
        "docx_redline.word_verify.shutil.which", lambda name: "/usr/local/bin/pdftoppm"
    )
    png_dir = tmp_path / "png"
    png_dir.mkdir()
    for stale in ("page-1.png", "page-2.png", "page-3.png", "page-4.png"):
        (png_dir / stale).write_bytes(b"stale")

    def fake_run(args: list[str]) -> _FakeResult:
        (png_dir / "page-1.png").write_bytes(b"fresh")
        (png_dir / "page-2.png").write_bytes(b"fresh")
        return _FakeResult(returncode=0)

    paths = _rasterize_pdf(tmp_path / "in.pdf", png_dir, fake_run)

    assert paths == [str(png_dir / "page-1.png"), str(png_dir / "page-2.png")]
    assert not (png_dir / "page-3.png").exists()
    assert not (png_dir / "page-4.png").exists()


def test_rasterize_pdf_raises_on_pdftoppm_failure(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "docx_redline.word_verify.shutil.which", lambda name: "/usr/local/bin/pdftoppm"
    )
    runner = _FakeRunner(results=[_FakeResult(returncode=1, stderr="bad pdf")])
    with pytest.raises(RedlineError, match="pdftoppm failed"):
        _rasterize_pdf(tmp_path / "in.pdf", tmp_path / "png", runner)


# --- verify_word end-to-end orchestration (all fakes) ------------------------


def test_verify_word_returns_result_and_writes_pdf_hash(
    monkeypatch, docx_factory, tmp_path: Path
) -> None:
    monkeypatch.setattr("docx_redline.word_verify.platform.system", lambda: "Darwin")
    docx = docx_factory("doc.docx", [["Plain text."]])
    package = DocxPackage(docx)
    pdf_path = tmp_path / "out.pdf"

    def fake_run(args: list[str]) -> _FakeResult:
        if args[0] == "osascript" and "id of application" in args[2]:
            return _FakeResult(returncode=0)
        pdf_path.write_bytes(b"%PDF-fake")
        return _FakeResult(returncode=0, stdout="16.78|2")

    result = verify_word(docx, pdf_path, package=package, runner=fake_run)

    assert result.word_version == "16.78"
    assert result.page_count == 2
    assert result.pdf_path == str(pdf_path)
    assert result.ok
    assert result.declared_fonts == []


def test_verify_word_resolves_relative_pdf_path_before_passing_to_word(
    monkeypatch, docx_factory, tmp_path: Path
) -> None:
    # Word resolves a relative "file name" against its own notion of the
    # current location, not this process's cwd - a relative --pdf must be
    # made absolute before reaching osascript, or the PDF can land somewhere
    # the caller never asked for.
    monkeypatch.setattr("docx_redline.word_verify.platform.system", lambda: "Darwin")
    monkeypatch.chdir(tmp_path)
    docx = docx_factory("doc.docx", [["Plain text."]])
    package = DocxPackage(docx)
    relative_pdf = Path("out.pdf")
    seen_pdf_arg: list[str] = []

    def fake_run(args: list[str]) -> _FakeResult:
        if args[0] == "osascript" and "id of application" in args[2]:
            return _FakeResult(returncode=0)
        seen_pdf_arg.append(args[-1])
        (tmp_path / "out.pdf").write_bytes(b"%PDF-fake")
        return _FakeResult(returncode=0, stdout="16.78|1")

    result = verify_word(docx, relative_pdf, package=package, runner=fake_run)

    assert seen_pdf_arg == [str((tmp_path / "out.pdf").resolve())]
    assert result.pdf_path == str((tmp_path / "out.pdf").resolve())


def test_verify_word_reports_missing_required_font_without_raising(
    monkeypatch, docx_factory, tmp_path: Path
) -> None:
    monkeypatch.setattr("docx_redline.word_verify.platform.system", lambda: "Darwin")
    docx = docx_factory("doc.docx", [["Plain text."]])
    package = DocxPackage(docx)
    pdf_path = tmp_path / "out.pdf"

    def fake_run(args: list[str]) -> _FakeResult:
        if args[0] == "osascript" and "id of application" in args[2]:
            return _FakeResult(returncode=0)
        pdf_path.write_bytes(b"%PDF-fake")
        return _FakeResult(returncode=0, stdout="16.78|1")

    result = verify_word(
        docx,
        pdf_path,
        package=package,
        required_fonts=["Times New Roman"],
        runner=fake_run,
    )

    assert not result.ok
    assert result.missing_required_fonts == ["Times New Roman"]


def test_verify_word_reports_unexpected_font(
    monkeypatch, docx_factory, tmp_path: Path
) -> None:
    monkeypatch.setattr("docx_redline.word_verify.platform.system", lambda: "Darwin")
    docx = docx_factory("doc.docx", [[("Body", '<w:rFonts w:ascii="Comic Sans MS"/>')]])
    package = DocxPackage(docx)
    pdf_path = tmp_path / "out.pdf"

    def fake_run(args: list[str]) -> _FakeResult:
        if args[0] == "osascript" and "id of application" in args[2]:
            return _FakeResult(returncode=0)
        pdf_path.write_bytes(b"%PDF-fake")
        return _FakeResult(returncode=0, stdout="16.78|1")

    result = verify_word(
        docx,
        pdf_path,
        package=package,
        expected_fonts=["Arial"],
        runner=fake_run,
    )

    assert not result.ok
    assert result.unexpected_fonts == ["Comic Sans MS"]


def test_verify_word_raises_off_macos_before_touching_word(
    monkeypatch, docx_factory, tmp_path: Path
) -> None:
    monkeypatch.setattr("docx_redline.word_verify.platform.system", lambda: "Linux")
    docx = docx_factory("doc.docx", [["Plain text."]])
    package = DocxPackage(docx)
    runner = _FakeRunner()

    with pytest.raises(RedlineError, match="macOS"):
        verify_word(docx, tmp_path / "out.pdf", package=package, runner=runner)
    assert runner.calls == []


def test_verify_word_raises_when_word_unavailable(
    monkeypatch, docx_factory, tmp_path: Path
) -> None:
    monkeypatch.setattr("docx_redline.word_verify.platform.system", lambda: "Darwin")
    docx = docx_factory("doc.docx", [["Plain text."]])
    package = DocxPackage(docx)
    runner = _FakeRunner(results=[_FakeResult(returncode=1, stderr="no such app")])

    with pytest.raises(RedlineError, match="not available"):
        verify_word(docx, tmp_path / "out.pdf", package=package, runner=runner)


def test_verify_word_raises_when_pdf_missing_after_reported_success(
    monkeypatch, docx_factory, tmp_path: Path
) -> None:
    monkeypatch.setattr("docx_redline.word_verify.platform.system", lambda: "Darwin")
    docx = docx_factory("doc.docx", [["Plain text."]])
    package = DocxPackage(docx)
    pdf_path = tmp_path / "out.pdf"

    def fake_run(args: list[str]) -> _FakeResult:
        if args[0] == "osascript" and "id of application" in args[2]:
            return _FakeResult(returncode=0)
        # Reports success but never writes the PDF.
        return _FakeResult(returncode=0, stdout="16.78|1")

    with pytest.raises(RedlineError, match="no PDF was written"):
        verify_word(docx, pdf_path, package=package, runner=fake_run)
