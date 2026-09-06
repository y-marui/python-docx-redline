"""Structural checks for comment plumbing and content preservation."""

from __future__ import annotations

from copy import deepcopy

from lxml import etree

from .errors import RedlineError
from .package import DocxPackage
from .pptx import (
    COMMENT_EXT,
    MODERN_REL,
    NS,
    PRESENTATION,
    Slide,
    TextTarget,
    object_targets,
    qn,
    relationships,
    resolve,
    slides,
    text_targets,
    utf16_length,
)


def _check_part(
    pkg: DocxPackage, part: str, kind: str, root_tag: str
) -> etree._Element:
    root = pkg.xml(part)
    types = [
        n.get("ContentType")
        for n in pkg.xml("[Content_Types].xml")
        if n.get("PartName") == "/" + part
    ]
    if types != [f"application/vnd.ms-powerpoint.{kind}+xml"]:
        raise RedlineError(f"Missing/invalid modern {kind} content type")
    if root.tag != qn(root_tag):
        raise RedlineError(f"Unexpected modern {kind} root")
    return root


def _authors(pkg: DocxPackage) -> set[str]:
    result = set()
    for rel in relationships(pkg, PRESENTATION):
        if rel.get("Type") == MODERN_REL + "authors":
            root = _check_part(
                pkg, resolve(PRESENTATION, rel), "authors", "p188:authorLst"
            )
            for author in root:
                author_id = author.attrib["id"]
                if author_id in result:
                    raise RedlineError("Duplicate author id")
                result.add(author_id)
    return result


def validate(pkg: DocxPackage, original: DocxPackage | None = None) -> int:
    author_ids = _authors(pkg)
    ids: set[str] = set()
    for slide in slides(pkg):
        rels = relationships(pkg, slide.part)
        modern = [r for r in rels if r.get("Type") == MODERN_REL + "comments"]
        if len(modern) > 1:
            raise RedlineError("Multiple modern comment parts on one slide")
        refs = slide.root.findall("p:extLst/p:ext/p188:commentRel", NS)
        if len(refs) != len(modern):
            raise RedlineError("Missing or orphaned modern comment reference")
        for rel in rels:
            if rel.get("Type") != MODERN_REL + "comments":
                continue
            refs = slide.root.findall("p:extLst/p:ext/p188:commentRel", NS)
            if sum(ref.get(qn("r:id")) == rel.get("Id") for ref in refs) != 1:
                raise RedlineError(
                    "Missing/duplicate modern comment extension reference"
                )
            root = _check_part(pkg, resolve(slide.part, rel), "comments", "p188:cmLst")
            for cm in root.findall("p188:cm", NS):
                _check_comment(cm, slide, author_ids, ids)
                text_anchor = cm.find("ac:txMkLst", NS)
                object_anchor = cm.find("ac:deMkLst", NS)
                if text_anchor is not None:
                    _check_range(text_anchor, text_targets(slide))
                if object_anchor is not None:
                    _check_object(object_anchor, slide)
    if original is not None:
        _preserved(pkg, original)
    return len(ids)


def _check_comment(
    cm: etree._Element, slide: Slide, authors: set[str], ids: set[str]
) -> None:
    comment_id = cm.attrib["id"]
    if comment_id in ids or cm.get("authorId") not in authors:
        raise RedlineError("Duplicate comment id or missing author")
    ids.add(comment_id)
    anchors = [
        c
        for c in cm
        if c.tag in (qn("ac:txMkLst"), qn("ac:deMkLst"), qn("pc:sldMkLst"))
    ]
    if len(anchors) != 1:
        raise RedlineError("Unsupported or missing comment anchor")
    slide_ref = anchors[0].find("pc:sldMk", NS)
    if slide_ref is None or slide_ref.get("sldId") != slide.slide_id:
        raise RedlineError("Comment points to a different slide")
    creation = slide.root.find("p:extLst/p:ext/p14:creationId", NS)
    if creation is not None and slide_ref.get("cId") != creation.get("val"):
        raise RedlineError("Comment slide creation ID is missing or mismatched")
    if cm.find("p188:txBody", NS) is None:
        raise RedlineError("Comment body is missing")


def _check_object(anchor: etree._Element, slide: Slide) -> None:
    if len(anchor) < 3:
        raise RedlineError("Incomplete drawing object anchor")
    moniker = anchor[-1]
    kinds = {qn("ac:spMk"): "shape", qn("ac:picMk"): "picture"}
    kind = kinds.get(moniker.tag)
    found = [
        target
        for target in object_targets(slide)
        if target.object_id == moniker.get("id") and target.kind == kind
    ]
    if len(found) != 1:
        raise RedlineError("Missing or ambiguous comment object")
    props_path = (
        "p:nvPicPr/p:cNvPr" if found[0].kind == "picture" else "p:nvSpPr/p:cNvPr"
    )
    props = found[0].element.find(props_path, NS)
    creation = props.find("a:extLst/a:ext/a16:creationId", NS)
    if creation is not None and moniker.get("creationId") != creation.get("id"):
        raise RedlineError("Comment object creation ID is missing or mismatched")


def _check_range(anchor: etree._Element, targets: list[TextTarget]) -> None:
    shape = anchor.find("ac:spMk", NS)
    span = anchor.find("ac:txMk", NS)
    if shape is None or span is None:
        raise RedlineError("Incomplete text range anchor")
    found = [t for t in targets if t.shape_id == shape.get("id")]
    if len(found) != 1:
        raise RedlineError("Missing/ambiguous comment shape")
    creation = found[0].shape.find("p:nvSpPr/p:cNvPr/a:extLst/a:ext/a16:creationId", NS)
    if creation is not None and shape.get("creationId") != creation.get("id"):
        raise RedlineError("Comment shape creation ID is missing or mismatched")
    start, length = int(span.attrib["cp"]), int(span.get("len", "0"))
    text = found[0].text
    if start < 0 or length <= 0 or start + length > utf16_length(text):
        raise RedlineError("Comment text range is out of bounds")
    try:
        text.encode("utf-16-le")[start * 2 : (start + length) * 2].decode("utf-16-le")
    except UnicodeDecodeError as error:
        raise RedlineError("Comment splits a Unicode surrogate pair") from error


def _slide_content(root: etree._Element) -> bytes:
    copy = deepcopy(root)
    ext_list = copy.find("p:extLst", NS)
    if ext_list is not None:
        for ext in list(ext_list):
            if ext.get("uri") == COMMENT_EXT:
                ext_list.remove(ext)
        if len(ext_list) == 0:
            copy.remove(ext_list)
    # Drop unused namespace declarations added with a comment extension.
    etree.cleanup_namespaces(copy)
    return bytes(etree.tostring(copy, method="c14n"))


def _preserved(pkg: DocxPackage, original: DocxPackage) -> None:
    original_slides = slides(original)
    if [(s.slide_id, s.part) for s in slides(pkg)] != [
        (s.slide_id, s.part) for s in original_slides
    ]:
        raise RedlineError("Slide order changed")
    slide_parts = {s.part for s in original_slides}
    for name in original.all_part_names():
        if not pkg.has_part(name):
            raise RedlineError(f"Original part removed: {name}")
        if name in slide_parts:
            if _slide_content(pkg.xml(name)) != _slide_content(original.xml(name)):
                raise RedlineError(f"Slide content changed: {name}")
        elif name.endswith(".rels") or name == "[Content_Types].xml":
            _existing_elements_preserved(pkg.xml(name), original.xml(name))
        elif name.startswith("ppt/comments/") or name == "ppt/authors.xml":
            _existing_elements_preserved(pkg.xml(name), original.xml(name))
        elif pkg.raw(name) != original.raw(name):
            raise RedlineError(f"Original part changed: {name}")


def _existing_elements_preserved(new: etree._Element, old: etree._Element) -> None:
    def signature(node: etree._Element) -> tuple[object, ...]:
        return (node.tag, dict(node.attrib), node.text, [signature(c) for c in node])

    remaining = [signature(c) for c in new]
    for node in old:
        item = signature(node)
        if item not in remaining:
            raise RedlineError("Existing package metadata/comment changed")
        remaining.remove(item)
