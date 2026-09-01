"""macOS-only layout verification via Microsoft Word automation, plus a
static font-declaration audit that needs neither macOS nor Word.

Word is driven through `osascript` (AppleScript) rather than a Python
automation library, so this module has no new runtime dependency beyond the
`osascript`/`pdftoppm` executables it shells out to. All subprocess calls go
through an injectable `runner` so command construction and error handling
are fully testable without macOS or Word installed (see the acceptance
criteria on https://github.com/y-marui/python-docx-redline/issues/10) - the
actual AppleScript dialogue with Word still needs verifying against a real
Word installation, which this module cannot do on its own.
"""

from __future__ import annotations

import hashlib
import platform
import shutil
import subprocess
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from .errors import RedlineError
from .ooxml import NSMAP, w
from .package import DocxPackage

Runner = Callable[[list[str]], "subprocess.CompletedProcess[str]"]


def _default_runner(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True)


@dataclass
class WordVerifyResult:
    word_version: str
    page_count: int
    pdf_path: str
    pdf_sha256: str
    png_paths: list[str] = field(default_factory=list)
    declared_fonts: list[str] = field(default_factory=list)
    missing_required_fonts: list[str] = field(default_factory=list)
    unexpected_fonts: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing_required_fonts and not self.unexpected_fonts


_FONT_ATTRS = ("ascii", "hAnsi", "eastAsia", "cs")


def audit_declared_fonts(package: DocxPackage) -> set[str]:
    """Every font name declared via `w:rFonts` in styles and runs.

    Covers `word/styles.xml` (default/style-level fonts, e.g. docDefaults and
    named styles) and `word/document.xml` (run-level overrides) - the two
    parts the issue asks this static audit to cover. Declarations alone
    can't prove Word didn't substitute an unavailable font at render time;
    that's what the Word-rendered PDF is for.
    """
    fonts: set[str] = set()
    part_names = ["word/document.xml"]
    if package.has_part("word/styles.xml"):
        part_names.append("word/styles.xml")
    for name in part_names:
        root = package.xml(name)
        for rfonts in root.xpath(".//w:rFonts", namespaces=NSMAP):
            for attr in _FONT_ATTRS:
                value = rfonts.get(w(attr))
                if value:
                    fonts.add(value)
    return fonts


def _check_platform() -> None:
    if platform.system() != "Darwin":
        raise RedlineError(
            "verify-word requires macOS with Microsoft Word installed; "
            f"detected platform: {platform.system()}"
        )


def _check_word_available(runner: Runner) -> None:
    result = runner(["osascript", "-e", 'id of application "Microsoft Word"'])
    if result.returncode != 0:
        raise RedlineError(
            "Microsoft Word is not available: osascript could not resolve "
            f"its application id ({result.stderr.strip() or 'no error output'})"
        )


def _applescript(input_path: Path, pdf_path: Path) -> str:
    """AppleScript that opens `input_path` read-only, repaginates it, exports
    `pdf_path`, and closes without saving - the input is never modified.

    Uses Word's `compute statistics ... statistic pages` command for the
    repaginated page count and `save as ... file format format PDF` for the
    export, per Microsoft Word's AppleScript scripting dictionary.
    """
    return f'''
on run
    set inputPath to POSIX file "{input_path}"
    set pdfPath to POSIX file "{pdf_path}"
    tell application "Microsoft Word"
        set wordVersion to version
        set theDoc to open inputPath with read only
        set pageCount to compute statistics theDoc statistic statistic pages
        save as theDoc file name pdfPath file format format PDF
        close theDoc saving no
    end tell
    return wordVersion & "|" & pageCount
end run
'''.strip()


def _run_applescript(
    input_path: Path, pdf_path: Path, runner: Runner
) -> tuple[str, int]:
    script = _applescript(input_path, pdf_path)
    result = runner(["osascript", "-e", script])
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RedlineError(f"Microsoft Word export failed: {detail}")
    try:
        word_version, page_count = result.stdout.strip().rsplit("|", 1)
        return word_version, int(page_count)
    except ValueError as error:
        raise RedlineError(
            f"could not parse Word's output: {result.stdout.strip()!r}"
        ) from error


def _rasterize_pdf(pdf_path: Path, png_dir: Path, runner: Runner) -> list[str]:
    if shutil.which("pdftoppm") is None:
        raise RedlineError(
            "--png-dir requires `pdftoppm` (poppler) on PATH; install it "
            "(e.g. `brew install poppler`) or omit --png-dir"
        )
    png_dir.mkdir(parents=True, exist_ok=True)
    prefix = png_dir / "page"
    result = runner(["pdftoppm", "-png", "-r", "150", str(pdf_path), str(prefix)])
    if result.returncode != 0:
        raise RedlineError(f"pdftoppm failed: {result.stderr.strip()}")
    return sorted(str(path) for path in png_dir.glob("page-*.png"))


def verify_word(
    input_path: Path,
    pdf_path: Path,
    *,
    package: DocxPackage,
    png_dir: Path | None = None,
    required_fonts: Iterable[str] = (),
    expected_fonts: Iterable[str] = (),
    runner: Runner | None = None,
) -> WordVerifyResult:
    """Verify `input_path`'s layout/pagination via Word and audit its fonts.

    `input_path` is opened read-only and never modified. Raises
    `RedlineError` for an unsupported platform, unavailable Word, or a
    failed export/rasterization - all conditions the caller can't recover
    from. A missing required font or an unexpected one is *not* raised;
    it's reported on the returned result (`.ok`), matching how `validate`
    reports check failures without aborting before showing the rest.
    """
    run = runner or _default_runner
    _check_platform()
    _check_word_available(run)

    declared = audit_declared_fonts(package)
    required = set(required_fonts)
    expected = set(expected_fonts)
    missing_required = sorted(required - declared)
    unexpected = sorted(declared - expected) if expected else []

    word_version, page_count = _run_applescript(input_path, pdf_path, run)
    if not pdf_path.exists():
        raise RedlineError(
            f"Word reported success but no PDF was written to {pdf_path}"
        )
    pdf_sha256 = hashlib.sha256(pdf_path.read_bytes()).hexdigest()

    png_paths: list[str] = []
    if png_dir is not None:
        png_paths = _rasterize_pdf(pdf_path, png_dir, run)

    return WordVerifyResult(
        word_version=word_version,
        page_count=page_count,
        pdf_path=str(pdf_path),
        pdf_sha256=pdf_sha256,
        png_paths=png_paths,
        declared_fonts=sorted(declared),
        missing_required_fonts=missing_required,
        unexpected_fonts=unexpected,
    )
