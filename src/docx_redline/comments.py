"""Adding, listing, and stripping Word comments (word/comments.xml + anchors)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from lxml import etree

from .ooxml import COMMENTS_REL_TYPE, CT_NS, NSMAP, REL_NS, qn, w
from .package import DocxPackage

COMMENTS_PART = "word/comments.xml"
RELS_PART = "word/_rels/document.xml.rels"
CONTENT_TYPES_PART = "[Content_Types].xml"


@dataclass
class Comment:
    comment_id: int
    author: str
    date: str
    text: str


def list_comments(package: DocxPackage) -> list[Comment]:
    if not package.has_part(COMMENTS_PART):
        return []
    root = package.xml(COMMENTS_PART)
    comments = []
    for node in root.xpath("./w:comment", namespaces=NSMAP):
        text = "".join(node.xpath(".//w:t/text()", namespaces=NSMAP))
        comments.append(
            Comment(
                comment_id=int(node.get(w("id"))),
                author=node.get(w("author")) or "",
                date=node.get(w("date")) or "",
                text=text,
            )
        )
    return comments


def _comments_root(package: DocxPackage) -> etree._Element:
    if package.has_part(COMMENTS_PART):
        return package.xml(COMMENTS_PART)
    root = etree.Element(w("comments"), nsmap={"w": NSMAP["w"]})
    package.new_xml(COMMENTS_PART, root)
    return root


def _ensure_plumbing(package: DocxPackage) -> None:
    content_types = package.xml(CONTENT_TYPES_PART)
    if not content_types.xpath(
        "./ct:Override[@PartName='/word/comments.xml']", namespaces={"ct": CT_NS}
    ):
        override = etree.SubElement(content_types, qn(CT_NS, "Override"))
        override.set("PartName", "/word/comments.xml")
        override.set(
            "ContentType",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml",
        )

    relationships = package.xml(RELS_PART)
    existing = relationships.xpath(
        "./rel:Relationship[@Type=$type]",
        namespaces={"rel": REL_NS},
        type=COMMENTS_REL_TYPE,
    )
    if existing:
        return
    ids = []
    for relationship in relationships.xpath(
        "./rel:Relationship", namespaces={"rel": REL_NS}
    ):
        rel_id = relationship.get("Id", "")
        if rel_id.startswith("rId") and rel_id[3:].isdigit():
            ids.append(int(rel_id[3:]))
    relationship = etree.SubElement(relationships, qn(REL_NS, "Relationship"))
    relationship.set("Id", f"rId{max(ids, default=0) + 1}")
    relationship.set("Type", COMMENTS_REL_TYPE)
    relationship.set("Target", "comments.xml")


def add_comment(
    package: DocxPackage,
    paragraph: etree._Element,
    text: str,
    *,
    author: str,
    when: str,
) -> int:
    """Anchor a new comment to the full span of `paragraph`."""
    comments_root = _comments_root(package)
    _ensure_plumbing(package)
    ids = [
        int(c.get(w("id")))
        for c in comments_root.xpath("./w:comment", namespaces=NSMAP)
    ]
    comment_id = max(ids, default=-1) + 1

    ppr = paragraph.find("w:pPr", namespaces=NSMAP)
    children = list(paragraph)
    start_index = 1 if ppr is not None and children and children[0] is ppr else 0
    range_start = etree.Element(w("commentRangeStart"))
    range_start.set(w("id"), str(comment_id))
    paragraph.insert(start_index, range_start)
    range_end = etree.Element(w("commentRangeEnd"))
    range_end.set(w("id"), str(comment_id))
    paragraph.append(range_end)
    reference_run = etree.SubElement(paragraph, w("r"))
    reference_rpr = etree.SubElement(reference_run, w("rPr"))
    etree.SubElement(reference_rpr, w("rStyle")).set(w("val"), "CommentReference")
    etree.SubElement(reference_run, w("commentReference")).set(w("id"), str(comment_id))

    comment = etree.SubElement(comments_root, w("comment"))
    comment.set(w("id"), str(comment_id))
    comment.set(w("author"), author)
    comment.set(w("date"), when)
    comment_paragraph = etree.SubElement(comment, w("p"))
    comment_run = etree.SubElement(comment_paragraph, w("r"))
    etree.SubElement(comment_run, w("t")).text = text
    return comment_id


def strip_comments(package: DocxPackage) -> None:
    """Remove every comment, its anchors, and the supporting plumbing."""
    for name in package.all_part_names():
        if name == "word/document.xml" or re.fullmatch(
            r"word/(header|footer)\d+\.xml", name
        ):
            root = package.xml(name)
            for tag in ("commentRangeStart", "commentRangeEnd", "commentReference"):
                for element in root.xpath(f".//w:{tag}", namespaces=NSMAP):
                    parent = element.getparent()
                    if parent is not None:
                        parent.remove(element)

    if package.has_part(RELS_PART):
        relationships = package.xml(RELS_PART)
        for relationship in list(relationships.findall(qn(REL_NS, "Relationship"))):
            if "comments" in (relationship.get("Type") or "").lower():
                relationships.remove(relationship)

    if package.has_part(CONTENT_TYPES_PART):
        content_types = package.xml(CONTENT_TYPES_PART)
        for override in list(content_types.findall(qn(CT_NS, "Override"))):
            if "comments" in (override.get("PartName") or "").lower():
                content_types.remove(override)

    for name in [
        n
        for n in package.all_part_names()
        if n.startswith("word/comments") and n.endswith(".xml")
    ]:
        package.delete_part(name)
