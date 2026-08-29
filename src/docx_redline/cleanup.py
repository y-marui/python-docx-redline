"""Removing formatting-only revision noise that clutters a tracked-change diff."""

from __future__ import annotations

from lxml import etree

from .ooxml import NSMAP


def strip_format_revisions(document: etree._Element) -> int:
    """Remove w:pPrChange markers (paragraph-formatting revision history)."""
    changes = document.xpath(".//w:pPrChange", namespaces=NSMAP)
    for change in changes:
        parent = change.getparent()
        if parent is not None:
            parent.remove(change)
    return len(changes)
