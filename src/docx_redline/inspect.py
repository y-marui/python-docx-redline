"""Dumping paragraphs with style, breaks, and revision-aware text for review."""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from .ooxml import NSMAP, w


@dataclass
class ParagraphInfo:
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
    paragraph: etree._Element, index: int, location: str
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
        index=index,
        location=location,
        style=style_name or "",
        page_break=page_break,
        section_break=section_break,
        insertions=len(paragraph.xpath(".//w:ins", namespaces=NSMAP)),
        deletions=len(paragraph.xpath(".//w:del", namespaces=NSMAP)),
        text=_revision_text(paragraph),
    )


def inspect_document(document: etree._Element) -> list[ParagraphInfo]:
    body = document.find("w:body", namespaces=NSMAP)
    if body is None:
        raise ValueError("word/document.xml has no w:body")
    infos: list[ParagraphInfo] = []
    table_number = 0
    index = 0
    for element in body:
        local = etree.QName(element).localname
        if local == "p":
            paragraphs, location = [element], "body"
        elif local == "tbl":
            table_number += 1
            paragraphs = element.xpath(".//w:p", namespaces=NSMAP)
            location = f"table-{table_number}"
        else:
            continue
        for paragraph in paragraphs:
            index += 1
            infos.append(_paragraph_info(paragraph, index, location))
    return infos
