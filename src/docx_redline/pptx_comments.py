"""PowerPoint modern comments anchored to exact OfficeArt text ranges."""

from __future__ import annotations

import posixpath
from uuid import uuid4

from lxml import etree

from .errors import RedlineError
from .ooxml import utc_timestamp
from .package import DocxPackage
from .pptx import (
    COMMENT_EXT,
    MODERN_REL,
    NS,
    PRESENTATION,
    ObjectTarget,
    Slide,
    TextTarget,
    child,
    find_object,
    find_target,
    qn,
    relationships,
    rels_name,
    resolve,
    slides,
)


def guid() -> str:
    return "{" + str(uuid4()).upper() + "}"


def _related_part(
    pkg: DocxPackage, source: str, kind: str, preferred: str, root_tag: str
) -> tuple[str, str]:
    rels = relationships(pkg, source)
    existing = [r for r in rels if r.get("Type") == MODERN_REL + kind]
    if len(existing) > 1:
        raise RedlineError(f"Multiple {kind} parts are not supported")
    if existing:
        part = resolve(source, existing[0])
        if pkg.xml(part).tag != qn(root_tag):
            raise RedlineError(f"Unexpected {kind} part root")
        return part, existing[0].attrib["Id"]
    if pkg.has_part(preferred):
        raise RedlineError(f"Unrelated part already exists: {preferred}")
    rel_name = rels_name(source)
    if not pkg.has_part(rel_name):
        pkg.new_xml(
            rel_name, etree.Element(qn("rel:Relationships"), nsmap={None: NS["rel"]})
        )
    ids = {r.get("Id") for r in rels}
    index = 1
    while f"rId{index}" in ids:
        index += 1
    rid = f"rId{index}"
    child(
        pkg.xml(rel_name),
        "rel:Relationship",
        Id=rid,
        Type=MODERN_REL + kind,
        Target=posixpath.relpath(preferred, posixpath.dirname(source)),
    )
    pkg.new_xml(preferred, etree.Element(qn(root_tag), nsmap=NS))
    types = pkg.xml("[Content_Types].xml")
    for node in types:
        if node.get("PartName") == "/" + preferred:
            raise RedlineError(f"Conflicting content type: {preferred}")
    child(
        types,
        "ct:Override",
        PartName="/" + preferred,
        ContentType=f"application/vnd.ms-powerpoint.{kind}+xml",
    )
    return preferred, rid


def _author(pkg: DocxPackage, name: str) -> str:
    if not name.strip():
        raise RedlineError("author must be non-empty")
    part, _ = _related_part(
        pkg, PRESENTATION, "authors", "ppt/authors.xml", "p188:authorLst"
    )
    root = pkg.xml(part)
    existing = [a for a in root if a.get("name") == name]
    if len(existing) > 1:
        raise RedlineError("Ambiguous existing comment author")
    if existing:
        return str(existing[0].attrib["id"])
    author_id = guid()
    child(
        root,
        "p188:author",
        id=author_id,
        name=name,
        initials="".join(word[0] for word in name.split()),
        userId=author_id,
        providerId="",
    )
    return author_id


def _slide_reference(parent: etree._Element, slide: Slide) -> None:
    child(parent, "pc:docMk")
    attrs = {"sldId": slide.slide_id}
    creation = slide.root.find("p:extLst/p:ext/p14:creationId", NS)
    if creation is not None:
        attrs["cId"] = creation.attrib["val"]
    child(parent, "pc:sldMk", **attrs)


def _creation_id(element: etree._Element, props_path: str) -> str | None:
    props = element.find(props_path, NS)
    if props is None:
        return None
    creation = props.find("a:extLst/a:ext/a16:creationId", NS)
    return creation.get("id") if creation is not None else None


def _anchor(
    cm: etree._Element,
    slide: Slide,
    target: TextTarget | ObjectTarget | None,
) -> None:
    if target is None:
        _slide_reference(child(cm, "pc:sldMkLst"), slide)
        return
    if isinstance(target, ObjectTarget):
        anchor = child(cm, "ac:deMkLst")
        _slide_reference(anchor, slide)
        tag = "ac:picMk" if target.kind == "picture" else "ac:spMk"
        props_path = (
            "p:nvPicPr/p:cNvPr" if target.kind == "picture" else "p:nvSpPr/p:cNvPr"
        )
        attrs = {"id": target.object_id}
        creation_id = _creation_id(target.element, props_path)
        if creation_id is not None:
            attrs["creationId"] = creation_id
        child(anchor, tag, **attrs)
        return
    anchor = child(cm, "ac:txMkLst")
    _slide_reference(anchor, slide)
    attrs = {"id": target.shape_id}
    creation = target.shape.find("p:nvSpPr/p:cNvPr/a:extLst/a:ext/a16:creationId", NS)
    if creation is not None:
        attrs["creationId"] = creation.attrib["id"]
    child(anchor, "ac:spMk", **attrs)
    # Context is optional; omit it rather than store a stale body hash.
    child(anchor, "ac:txMk", cp=str(target.start), len=str(target.length))


def _extension(slide: Slide, rid: str) -> None:
    ext_list = slide.root.find("p:extLst", NS)
    if ext_list is None:
        ext_list = child(slide.root, "p:extLst")
    entries = [e for e in ext_list if e.get("uri") == COMMENT_EXT]
    if len(entries) > 1:
        raise RedlineError("Duplicate modern comment extensions")
    ext = entries[0] if entries else child(ext_list, "p:ext", uri=COMMENT_EXT)
    refs = ext.findall("p188:commentRel", NS)
    if refs:
        if len(refs) != 1 or refs[0].get(qn("r:id")) != rid:
            raise RedlineError("Conflicting modern comment relationship")
    else:
        child(ext, "p188:commentRel", **{qn("r:id"): rid})


def add_comment(
    pkg: DocxPackage,
    text: str,
    *,
    author: str,
    match: str | None = None,
    slide: int | None = None,
    shape_id: str | None = None,
    object_id: str | None = None,
    occurrence: int | None = None,
    slide_level: bool = False,
) -> str:
    if not text.strip():
        raise RedlineError("Comment text must be non-empty")
    target: TextTarget | ObjectTarget | None = None
    if slide_level:
        if (
            slide is None
            or match is not None
            or shape_id
            or object_id
            or occurrence is not None
        ):
            raise RedlineError(
                "slide_level requires only a slide number, no text selector"
            )
        found = [s for s in slides(pkg) if s.number == slide]
        if not found:
            raise RedlineError("Slide number out of range")
        selected = found[0]
    elif object_id is not None:
        if slide is None or match is not None or shape_id or occurrence is not None:
            raise RedlineError("object_id requires a slide and no text selector")
        target = find_object(pkg, object_id, slide=slide)
        selected = target.slide
    else:
        target = find_target(
            pkg, match or "", slide=slide, shape_id=shape_id, occurrence=occurrence
        )
        selected = target.slide
    return _write_comment(pkg, selected, target, text, author)


def _write_comment(
    pkg: DocxPackage,
    selected: Slide,
    target: TextTarget | ObjectTarget | None,
    text: str,
    author: str,
) -> str:
    author_id = _author(pkg, author)
    part, rid = _related_part(
        pkg,
        selected.part,
        "comments",
        f"ppt/comments/redline{selected.slide_id}.xml",
        "p188:cmLst",
    )
    _extension(selected, rid)
    comment_id = guid()
    cm = child(
        pkg.xml(part),
        "p188:cm",
        id=comment_id,
        authorId=author_id,
        created=utc_timestamp(),
    )
    _anchor(cm, selected, target)
    body = child(cm, "p188:txBody")
    child(body, "a:bodyPr")
    child(body, "a:lstStyle")
    for line in text.split("\n"):
        run = child(child(body, "a:p"), "a:r")
        child(run, "a:t").text = line
    return comment_id


def apply_batch(pkg: DocxPackage, entries: object, *, author: str) -> list[str]:
    if not isinstance(entries, list) or not entries:
        raise RedlineError("comments must be a non-empty JSON array")
    ids = []
    allowed = {
        "text",
        "match",
        "slide",
        "shape_id",
        "object_id",
        "occurrence",
        "slide_level",
    }
    for index, entry in enumerate(entries, 1):
        if not isinstance(entry, dict) or set(entry) - allowed:
            raise RedlineError(f"Comment {index}: invalid fields")
        for key in ("text", "match", "shape_id", "object_id"):
            if key in entry and not isinstance(entry[key], str):
                raise RedlineError(f"Comment {index}: {key} must be a string")
        for key in ("slide", "occurrence"):
            if key in entry and (type(entry[key]) is not int or entry[key] < 1):
                raise RedlineError(f"Comment {index}: {key} must be a positive integer")
        if "slide_level" in entry and type(entry["slide_level"]) is not bool:
            raise RedlineError(f"Comment {index}: slide_level must be boolean")
        if "text" not in entry:
            raise RedlineError(f"Comment {index}: text is required")
        ids.append(add_comment(pkg, author=author, **entry))
    return ids


def list_comments(pkg: DocxPackage) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for slide in slides(pkg):
        for rel in relationships(pkg, slide.part):
            if rel.get("Type") not in (MODERN_REL + "comments", NS["r"] + "/comments"):
                continue
            part = resolve(slide.part, rel)
            for cm in pkg.xml(part):
                modern = cm.tag == qn("p188:cm")
                if cm.tag not in (qn("p188:cm"), qn("p:cm")):
                    continue
                shape = cm.find("ac:txMkLst/ac:spMk", NS)
                span = cm.find("ac:txMkLst/ac:txMk", NS)
                drawing = cm.find("ac:deMkLst", NS)
                drawing_target = drawing[-1] if drawing is not None else None
                body = cm.find("p188:txBody", NS)
                text = (
                    "\n".join("".join(p.itertext()) for p in body.findall("a:p", NS))
                    if body is not None
                    else cm.findtext("p:text", "", NS)
                )
                result.append(
                    dict(
                        slide=slide.number,
                        part=part,
                        id=cm.get("id" if modern else "idx"),
                        author_id=cm.get("authorId"),
                        modern=modern,
                        text=text,
                        shape_id=shape.get("id") if shape is not None else None,
                        start=int(span.attrib["cp"]) if span is not None else None,
                        length=int(span.get("len", "0")) if span is not None else None,
                        object_id=(
                            drawing_target.get("id")
                            if drawing_target is not None
                            else None
                        ),
                        object_kind=(
                            etree.QName(drawing_target).localname
                            if drawing_target is not None
                            else None
                        ),
                    )
                )
    return result
