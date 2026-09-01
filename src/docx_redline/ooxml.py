"""Low-level OOXML (WordprocessingML) namespace and node helpers."""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, cast

from lxml import etree

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
XML_NS = "http://www.w3.org/XML/1998/namespace"
COMMENTS_REL_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
)
NSMAP = {"w": W_NS, "rel": REL_NS, "ct": CT_NS}


def w(local: str) -> str:
    return f"{{{W_NS}}}{local}"


def qn(namespace: str, local: str) -> str:
    return f"{{{namespace}}}{local}"


def xml_bytes(root: etree._Element) -> bytes:
    return cast(
        bytes,
        etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True),
    )


def utc_timestamp() -> str:
    """Word revision timestamp: UTC, second precision, trailing 'Z'."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class IdAllocator:
    """Hands out w:id values that never collide with ids already in the document."""

    def __init__(self, start: int) -> None:
        self._next = start

    def take(self) -> int:
        value = self._next
        self._next += 1
        return value


def next_change_id(
    documents: etree._Element | Iterable[etree._Element],
) -> IdAllocator:
    """Seed an allocator past every `w:id` already used in `documents`.

    Accepts either a single part root or several (e.g. the document body plus
    headers/footers/footnotes/endnotes), so ids stay unique across every part
    a multi-part edit might touch, not just the one being scanned.
    """
    roots = [documents] if isinstance(documents, etree._Element) else documents
    ids: list[int] = []
    for document in roots:
        for element in document.xpath(".//*[@w:id]", namespaces=NSMAP):
            try:
                ids.append(int(element.get(w("id"))))
            except (TypeError, ValueError):
                continue
    return IdAllocator(max(ids, default=0) + 1)


def enable_tracking(settings: etree._Element) -> None:
    if settings.find("w:trackRevisions", namespaces=NSMAP) is None:
        settings.insert(0, etree.Element(w("trackRevisions")))


def set_text(node: etree._Element, value: str) -> None:
    node.text = value
    if value[:1].isspace() or value[-1:].isspace():
        node.set(qn(XML_NS, "space"), "preserve")


def make_run(
    rpr: etree._Element | None, value: str, *, deleted: bool = False
) -> etree._Element:
    run = etree.Element(w("r"))
    if rpr is not None:
        run.append(deepcopy(rpr))
    text_node = etree.SubElement(run, w("delText") if deleted else w("t"))
    set_text(text_node, value)
    return run


def make_tracked_wrapper(
    kind: str, change_id: int, author: str, when: str
) -> etree._Element:
    """A bare w:ins or w:del wrapper; caller appends one or more w:r runs."""
    wrapper = etree.Element(w(kind))
    wrapper.set(w("id"), str(change_id))
    wrapper.set(w("author"), author)
    wrapper.set(w("date"), when)
    return wrapper


def make_change(
    kind: str,
    change_id: int,
    author: str,
    when: str,
    rpr: etree._Element | None,
    value: str,
) -> etree._Element:
    """A w:ins/w:del wrapper containing a single run - the common case."""
    wrapper = make_tracked_wrapper(kind, change_id, author, when)
    wrapper.append(make_run(rpr, value, deleted=(kind == "del")))
    return wrapper


RprSignature = tuple[Any, ...]

# ST_OnOff toggle properties (OOXML ECMA-376 17.3.2): the element's meaning is
# a plain boolean, encoded several equivalent ways - <w:b/>, <w:b w:val="1"/>,
# <w:b w:val="true"/>, and <w:b w:val="on"/> all mean "bold on". Compared as
# raw attributes these would wrongly look different; normalize them instead.
_TOGGLE_PROPERTIES = frozenset(
    {
        "b",
        "bCs",
        "i",
        "iCs",
        "caps",
        "smallCaps",
        "strike",
        "dstrike",
        "emboss",
        "imprint",
        "outline",
        "shadow",
        "vanish",
        "webHidden",
        "noProof",
        "snapToGrid",
        "specVanish",
        "rtl",
        "cs",
        "oMath",
    }
)
_ON_OFF_FALSE_VALUES = frozenset({"0", "false", "off"})


def rpr_signature(rpr: etree._Element | None) -> RprSignature:
    """Canonical, order-independent signature of a w:rPr's effective formatting.

    Two runs compare equal here exactly when Word would render them
    identically: same bold/italic/underline/strike, vertical alignment
    (sub/superscript), character style, fonts, size, color, and any other
    w:rPr child. `w:rPrChange` is excluded because it records the *prior*
    formatting for a tracked format-only change, not the run's current
    appearance. ST_OnOff toggles (bold, italic, etc.) are normalized to a
    plain boolean so equivalent encodings (`<w:b/>`, `w:val="1"`, `"true"`,
    `"on"`) compare equal.
    """
    if rpr is None:
        return ()

    def canonical(element: etree._Element) -> RprSignature:
        local = etree.QName(element).localname
        if local in _TOGGLE_PROPERTIES:
            value = element.get(w("val"))
            enabled = value is None or value.lower() not in _ON_OFF_FALSE_VALUES
            return (element.tag, enabled)
        attrs = tuple(sorted(element.attrib.items()))
        children = tuple(sorted(canonical(child) for child in element))
        return (element.tag, attrs, children)

    return tuple(
        sorted(
            canonical(child)
            for child in rpr
            if etree.QName(child).localname != "rPrChange"
        )
    )


def apply_bold(rpr: etree._Element | None, bold: bool | None) -> etree._Element | None:
    """Force w:b/w:bCs on or off. `bold=None` leaves rpr untouched."""
    if bold is None:
        return rpr
    result = rpr if rpr is not None else etree.Element(w("rPr"))
    for tag in ("b", "bCs"):
        existing = result.find(f"w:{tag}", namespaces=NSMAP)
        if bold and existing is None:
            result.append(etree.Element(w(tag)))
        elif not bold and existing is not None:
            result.remove(existing)
    return result
