"""In-memory view of a .docx zip package, edited part-by-part."""

from __future__ import annotations

import zipfile
from pathlib import Path

from lxml import etree

from .ooxml import W_NS, xml_bytes


class DocxPackage:
    def __init__(self, path: Path) -> None:
        self.path = path
        with zipfile.ZipFile(path) as archive:
            self._infolist = archive.infolist()
            self._parts: dict[str, bytes] = {
                info.filename: archive.read(info.filename) for info in self._infolist
            }
        self._roots: dict[str, etree._Element] = {}
        self._extra_names: list[str] = []

    def has_part(self, name: str) -> bool:
        return name in self._parts

    def all_part_names(self) -> list[str]:
        return list(self._parts.keys())

    def raw(self, name: str) -> bytes:
        return self._parts[name]

    def xml(self, name: str) -> etree._Element:
        if name not in self._roots:
            self._roots[name] = etree.fromstring(self._parts[name])
        return self._roots[name]

    def editable_text_parts(self) -> list[tuple[str, etree._Element]]:
        """Word body-text parts open to proofreading commands.

        The main document plus headers, footers, footnotes, and endnotes -
        not `word/comments.xml`, which has its own dedicated
        `add-comment`/`list-comments` surface.
        """
        names = {"word/document.xml", "word/footnotes.xml", "word/endnotes.xml"}
        parts: list[tuple[str, etree._Element]] = []
        for name in self.all_part_names():
            is_header_or_footer = name.startswith(("word/header", "word/footer"))
            if name not in names and not is_header_or_footer:
                continue
            root = self.xml(name)
            if etree.QName(root).namespace == W_NS:
                parts.append((name, root))
        return parts

    def new_xml(self, name: str, root: etree._Element) -> None:
        """Register a brand-new XML part (e.g. comments.xml) missing from the source."""
        if name not in self._parts:
            self._extra_names.append(name)
        self._roots[name] = root
        self._parts[name] = b""

    def delete_part(self, name: str) -> None:
        self._parts.pop(name, None)
        self._roots.pop(name, None)

    def _current_bytes(self, name: str) -> bytes:
        if name in self._roots:
            return xml_bytes(self._roots[name])
        return self._parts[name]

    def save(self, out_path: Path) -> None:
        if out_path.resolve() == self.path.resolve():
            raise ValueError("output path must differ from the input path")
        written: set[str] = set()
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for info in self._infolist:
                if info.filename not in self._parts:
                    continue
                archive.writestr(info, self._current_bytes(info.filename))
                written.add(info.filename)
            for name in self._extra_names:
                if name in self._parts and name not in written:
                    archive.writestr(name, self._current_bytes(name))
