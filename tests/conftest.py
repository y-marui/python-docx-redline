"""Builds minimal, from-scratch .docx fixtures - no python-docx dependency needed."""

from __future__ import annotations

import zipfile
from collections.abc import Sequence
from pathlib import Path

import pytest

CONTENT_TYPES = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>
</Types>"""

ROOT_RELS = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

DOCUMENT_RELS = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
</Relationships>"""

SETTINGS = (
    b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    b'<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    b"</w:settings>"
)


RunSpec = str | tuple[str, str]
"""A run is either plain text, or (text, rPr child XML) for formatted runs.

e.g. `("bold", "<w:b/>")` or `("sup", '<w:vertAlign w:val="superscript"/>')`.
"""


def _run_xml(run: RunSpec) -> str:
    if isinstance(run, tuple):
        text, rpr_xml = run
        rpr = f"<w:rPr>{rpr_xml}</w:rPr>" if rpr_xml else ""
        return f'<w:r>{rpr}<w:t xml:space="preserve">{text}</w:t></w:r>'
    return f'<w:r><w:t xml:space="preserve">{run}</w:t></w:r>'


def _paragraph_xml(runs: Sequence[RunSpec]) -> str:
    run_xml = "".join(_run_xml(run) for run in runs)
    return f"<w:p>{run_xml}</w:p>"


def build_document_xml(paragraphs: Sequence[Sequence[RunSpec]]) -> bytes:
    body = "".join(_paragraph_xml(runs) for runs in paragraphs)
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}<w:sectPr/></w:body></w:document>"
    )
    return xml.encode("utf-8")


def write_docx(path: Path, paragraphs: Sequence[Sequence[RunSpec]]) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", ROOT_RELS)
        archive.writestr("word/document.xml", build_document_xml(paragraphs))
        archive.writestr("word/settings.xml", SETTINGS)
        archive.writestr("word/_rels/document.xml.rels", DOCUMENT_RELS)
    return path


@pytest.fixture
def docx_factory(tmp_path: Path):
    def _make(name: str, paragraphs: Sequence[Sequence[RunSpec]]) -> Path:
        return write_docx(tmp_path / name, paragraphs)

    return _make


@pytest.fixture
def sample_docx(tmp_path: Path) -> Path:
    paragraphs = [
        ["This is the first paragraph."],
        ["軌道", "トルク", "の起源"],
        ["Repeated phrase.", " Repeated phrase."],
        ["Value is 42 nm and 3.5%."],
    ]
    return write_docx(tmp_path / "sample.docx", paragraphs)
