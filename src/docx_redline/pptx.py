"""Presentation discovery and exact text selection; no slide rendering required."""

from __future__ import annotations

import posixpath
from dataclasses import dataclass

from lxml import etree

from .errors import RedlineError
from .package import DocxPackage

NS = {
    "p14": "http://schemas.microsoft.com/office/powerpoint/2010/main",
    "a14": "http://schemas.microsoft.com/office/drawing/2010/main",
    "a16": "http://schemas.microsoft.com/office/drawing/2014/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
    "pc": "http://schemas.microsoft.com/office/powerpoint/2013/main/command",
    "ac": "http://schemas.microsoft.com/office/drawing/2013/main/command",
    "p188": "http://schemas.microsoft.com/office/powerpoint/2018/8/main",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
}
PRESENTATION = "ppt/presentation.xml"
MODERN_REL = "http://schemas.microsoft.com/office/2018/10/relationships/"
COMMENT_EXT = "{6950BFC3-D8DA-4A85-94F7-54DA5524770B}"


def qn(name: str) -> str:
    prefix, local = name.split(":")
    return f"{{{NS[prefix]}}}{local}"


def child(parent: etree._Element, tag: str, **attrs: str) -> etree._Element:
    return etree.SubElement(parent, qn(tag), attrs)


def rels_name(part: str) -> str:
    folder, name = posixpath.split(part)
    return f"{folder}/_rels/{name}.rels"


def relationships(pkg: DocxPackage, part: str) -> list[etree._Element]:
    name = rels_name(part)
    return list(pkg.xml(name)) if pkg.has_part(name) else []


def resolve(part: str, rel: etree._Element) -> str:
    if rel.get("TargetMode", "Internal") != "Internal":
        raise RedlineError("External package relationship is not supported")
    target = rel.get("Target", "")
    name = posixpath.normpath(posixpath.join(posixpath.dirname(part), target))
    if target.startswith("/"):
        name = target.lstrip("/")
    if not target or name.startswith("../"):
        raise RedlineError("Invalid package relationship target")
    return name


@dataclass
class Slide:
    number: int
    slide_id: str
    part: str
    root: etree._Element


def slides(pkg: DocxPackage) -> list[Slide]:
    if not pkg.has_part(PRESENTATION):
        raise RedlineError("Not a supported PresentationML package")
    rels = {r.get("Id"): r for r in relationships(pkg, PRESENTATION)}
    result = []
    for number, item in enumerate(
        pkg.xml(PRESENTATION).findall("p:sldIdLst/p:sldId", NS), 1
    ):
        rel = rels.get(item.get(qn("r:id")))
        if rel is None or rel.get("Type") != NS["r"] + "/slide":
            raise RedlineError(f"Missing slide relationship at slide {number}")
        part = resolve(PRESENTATION, rel)
        result.append(Slide(number, item.attrib["id"], part, pkg.xml(part)))
    return result


def office_text(body: etree._Element) -> str:
    """OfficeArt returns separate paragraphs; soft breaks occupy one character.

    An inserted equation (a14:m) carries no plain text of its own; it becomes
    a single placeholder character (U+FFFC, the conventional stand-in for an
    embedded non-text object) so the surrounding runs a paragraph mixes it
    with - e.g. "h: Planck constant" - stay anchorable by exact text.
    """
    paragraphs = []
    for para in body.findall("a:p", NS):
        chunks = []
        for node in para:
            if node.tag in (qn("a:r"), qn("a:fld")):
                chunks.append(node.findtext("a:t", default="", namespaces=NS))
            elif node.tag == qn("a:br"):
                chunks.append("\v")
            elif node.tag == qn("a14:m"):
                chunks.append("￼")
            elif node.tag not in (qn("a:pPr"), qn("a:endParaRPr")):
                raise RedlineError(
                    "Unsupported text content (e.g. math/alternate content)"
                )
        paragraphs.append("".join(chunks))
    return "\r".join(paragraphs)


def utf16_length(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


@dataclass
class TextTarget:
    slide: Slide
    shape_id: str
    shape_name: str
    text: str
    shape: etree._Element
    start: int = 0
    length: int = 0

    def info(self) -> dict[str, str | int]:
        return dict(
            slide=self.slide.number,
            part=self.slide.part,
            shape_id=self.shape_id,
            shape_name=self.shape_name,
            text=self.text,
            start=self.start,
            length=self.length,
        )


@dataclass
class ObjectTarget:
    slide: Slide
    object_id: str
    object_name: str
    kind: str
    element: etree._Element

    def info(self) -> dict[str, str | int]:
        return {
            "slide": self.slide.number,
            "part": self.slide.part,
            "object_id": self.object_id,
            "object_name": self.object_name,
            "kind": self.kind,
        }


def top_level_shapes(slide: Slide) -> list[etree._Element]:
    """Direct spTree children, standing in for mc:AlternateContent wrappers.

    PowerPoint wraps a shape in mc:AlternateContent instead of placing it
    directly under spTree when saving something that needs an extension the
    base schema lacks - e.g. a shape holding an inserted equation (a14:m).
    The mc:Choice branch is what every supported PowerPoint version actually
    renders and edits; mc:Fallback exists only for consumers missing that
    extension and typically holds an unhelpful static picture instead, so it
    is used only when no mc:Choice is present.
    """
    spTree = slide.root.find("p:cSld/p:spTree", NS)
    result = []
    for node in spTree:
        if node.tag != qn("mc:AlternateContent"):
            result.append(node)
            continue
        branch = node.find("mc:Choice", NS)
        if branch is None:
            branch = node.find("mc:Fallback", NS)
        if branch is not None:
            result.extend(branch)
    return result


def object_targets(slide: Slide) -> list[ObjectTarget]:
    result = []
    kinds = {
        qn("p:sp"): ("shape", "p:nvSpPr/p:cNvPr"),
        qn("p:pic"): ("picture", "p:nvPicPr/p:cNvPr"),
    }
    shapes = top_level_shapes(slide)
    for tag, (kind, props_path) in kinds.items():
        for element in shapes:
            if element.tag != tag:
                continue
            props = element.find(props_path, NS)
            if props is not None:
                result.append(
                    ObjectTarget(
                        slide,
                        props.attrib["id"],
                        props.get("name", ""),
                        kind,
                        element,
                    )
                )
    return result


def find_object(pkg: DocxPackage, object_id: str, *, slide: int) -> ObjectTarget:
    found = [
        target
        for item in slides(pkg)
        if item.number == slide
        for target in object_targets(item)
        if target.object_id == object_id
    ]
    if len(found) != 1:
        raise RedlineError("Object ID is missing or ambiguous on the selected slide")
    return found[0]


def text_targets(slide: Slide) -> list[TextTarget]:
    result = []
    # Only ordinary top-level shapes (including ones PowerPoint moved into
    # mc:AlternateContent, resolved by top_level_shapes): tables and grouped
    # text need different moniker paths and must not be guessed.
    for shape in top_level_shapes(slide):
        if shape.tag != qn("p:sp"):
            continue
        props = shape.find("p:nvSpPr/p:cNvPr", NS)
        body = shape.find("p:txBody", NS)
        if props is None or body is None:
            continue
        try:
            text = office_text(body)
        except RedlineError:
            continue
        result.append(
            TextTarget(slide, props.attrib["id"], props.get("name", ""), text, shape)
        )
    return result


def find_target(
    pkg: DocxPackage,
    match: str,
    *,
    slide: int | None = None,
    shape_id: str | None = None,
    occurrence: int | None = None,
) -> TextTarget:
    if not match:
        raise RedlineError("match must be non-empty")
    if occurrence is not None and occurrence < 1:
        raise RedlineError("occurrence must be 1 or greater")
    matches = []
    for item in slides(pkg):
        if slide is not None and item.number != slide:
            continue
        for target in text_targets(item):
            if shape_id is not None and target.shape_id != shape_id:
                continue
            start = target.text.find(match)
            while start != -1:
                matches.append(
                    TextTarget(
                        item,
                        target.shape_id,
                        target.shape_name,
                        target.text,
                        target.shape,
                        utf16_length(target.text[:start]),
                        utf16_length(match),
                    )
                )
                start = target.text.find(match, start + 1)
    if not matches:
        raise RedlineError(f"Text not found in supported slide shapes: {match!r}")
    if occurrence is None and len(matches) != 1:
        raise RedlineError(f"Ambiguous text: {len(matches)} matches; narrow the target")
    index = (occurrence or 1) - 1
    if index >= len(matches):
        raise RedlineError("occurrence exceeds match count")
    return matches[index]
