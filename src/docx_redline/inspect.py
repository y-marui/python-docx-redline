"""Dumping paragraphs with style, breaks, and revision-aware text for review."""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from .ooxml import NSMAP, w
from .package import DocxPackage


@dataclass
class ParagraphInfo:
    part: str
    index: int
    location: str
    style: str
    page_break: bool
    section_break: bool
    insertions: int
    deletions: int
    text: str


def _revision_text(paragraph: etree._Element) -> str:
    """Text with [DEL:...]/[INS:...] markers, readable without opening Word."""
    pieces: list[str] = []
    for node in paragraph.iter():
        local = etree.QName(node).localname
        if local == "t" and node.text:
            in_ins = node.xpath("boolean(ancestor::w:ins)", namespaces=NSMAP)
            pieces.append(f"[INS:{node.text}]" if in_ins else node.text)
        elif local == "delText" and node.text:
            pieces.append(f"[DEL:{node.text}]")
        elif local == "tab":
            pieces.append("\t")
        elif local in {"br", "cr"}:
            pieces.append("[BR]")
    return "".join(pieces)


def _paragraph_info(
    paragraph: etree._Element, part: str, index: int, location: str
) -> ParagraphInfo:
    style = paragraph.find("w:pPr/w:pStyle", namespaces=NSMAP)
    style_name = style.get(w("val")) if style is not None else ""
    page_break = bool(
        paragraph.xpath(
            ".//w:br[@w:type='page'] | ./w:pPr/w:pageBreakBefore", namespaces=NSMAP
        )
    )
    section_break = paragraph.find("w:pPr/w:sectPr", namespaces=NSMAP) is not None
    return ParagraphInfo(
        part=part,
        index=index,
        location=location,
        style=style_name or "",
        page_break=page_break,
        section_break=section_break,
        insertions=len(paragraph.xpath(".//w:ins", namespaces=NSMAP)),
        deletions=len(paragraph.xpath(".//w:del", namespaces=NSMAP)),
        text=_revision_text(paragraph),
    )


def _containers(root: etree._Element) -> list[tuple[etree._Element, str | None]]:
    """The (container, note_id) pairs to walk for paragraphs in `root`.

    - `word/document.xml`: a single container, the `w:body`, `note_id=None`.
    - headers/footers (`w:hdr`/`w:ftr`): the root itself is the container,
      `note_id=None` - their paragraphs sit directly under it, same as a
      document body.
    - footnotes/endnotes (`w:footnotes`/`w:endnotes`): one container per
      `w:footnote`/`w:endnote` child, `note_id` set from its `w:id` so a
      paragraph can be traced back to which note it's in.

    `note_id` is `None` (rather than e.g. `"body"`) for the document/header/
    footer case specifically so `inspect_document`'s established `location`
    values ("body", "table-N") for a document-body paragraph are unchanged -
    `docs/specification.md` documents `table-N` as a stable, machine-readable
    contract.
    """
    local = etree.QName(root).localname
    if local == "document":
        body = root.find("w:body", namespaces=NSMAP)
        if body is None:
            raise ValueError("word/document.xml has no w:body")
        return [(body, None)]
    if local in ("hdr", "ftr"):
        return [(root, None)]
    if local in ("footnotes", "endnotes"):
        note_tag = "footnote" if local == "footnotes" else "endnote"
        return [
            (note, f"{note_tag}-{note.get(w('id'), '?')}")
            for note in root.xpath(f"./w:{note_tag}", namespaces=NSMAP)
        ]
    raise ValueError(f"unsupported WordprocessingML root: {local!r}")


def inspect_document(
    root: etree._Element, *, part: str = "word/document.xml"
) -> list[ParagraphInfo]:
    infos: list[ParagraphInfo] = []
    index = 0
    for container, note_id in _containers(root):
        table_number = 0
        for element in container:
            local = etree.QName(element).localname
            if local == "p":
                paragraphs = [element]
                location = note_id if note_id is not None else "body"
            elif local == "tbl":
                table_number += 1
                paragraphs = element.xpath(".//w:p", namespaces=NSMAP)
                table_location = f"table-{table_number}"
                location = (
                    f"{note_id}/{table_location}"
                    if note_id is not None
                    else table_location
                )
            else:
                continue
            for paragraph in paragraphs:
                index += 1
                infos.append(_paragraph_info(paragraph, part, index, location))
    return infos


def inspect_package(package: DocxPackage) -> list[ParagraphInfo]:
    """Dump every paragraph across all editable text parts.

    See `DocxPackage.editable_text_parts` for what's covered. Paragraph
    `index` is renumbered sequentially across parts so each row has a
    unique, stable position in the combined listing.
    """
    infos: list[ParagraphInfo] = []
    for part, root in package.editable_text_parts():
        infos.extend(inspect_document(root, part=part))
    for position, info in enumerate(infos, start=1):
        info.index = position
    return infos
