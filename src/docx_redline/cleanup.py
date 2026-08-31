"""Clean up or accept existing Word revision markup."""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from .ooxml import NSMAP, w


@dataclass
class AcceptedRevisions:
    """Counts of revision nodes accepted from one WordprocessingML part."""

    insertions: int = 0
    deletions: int = 0
    property_changes: int = 0
    empty_paragraphs: int = 0

    def add(self, other: AcceptedRevisions) -> None:
        """Add counts from another processed part."""
        self.insertions += other.insertions
        self.deletions += other.deletions
        self.property_changes += other.property_changes
        self.empty_paragraphs += other.empty_paragraphs


def strip_format_revisions(document: etree._Element) -> int:
    """Remove w:pPrChange markers (paragraph-formatting revision history)."""
    changes = document.xpath(".//w:pPrChange", namespaces=NSMAP)
    for change in changes:
        parent = change.getparent()
        if parent is not None:
            parent.remove(change)
    return len(changes)


def accept_revisions(document: etree._Element) -> AcceptedRevisions:
    """Accept text, move, and property revisions in one WordprocessingML tree."""
    accepted = AcceptedRevisions()
    emptied_paragraphs: list[etree._Element] = []
    for deletion in document.xpath(".//w:del | .//w:moveFrom", namespaces=NSMAP):
        paragraph = deletion.getparent()
        while paragraph is not None and paragraph.tag != w("p"):
            paragraph = paragraph.getparent()
        if paragraph is not None:
            emptied_paragraphs.append(paragraph)
        parent = deletion.getparent()
        if parent is not None:
            parent.remove(deletion)
            accepted.deletions += 1

    for insertion in document.xpath(".//w:ins | .//w:moveTo", namespaces=NSMAP):
        parent = insertion.getparent()
        if parent is None:
            continue
        index = parent.index(insertion)
        for child in list(insertion):
            insertion.remove(child)
            parent.insert(index, child)
            index += 1
        parent.remove(insertion)
        accepted.insertions += 1

    changes = document.xpath(".//*[contains(local-name(), 'Change')]", namespaces=NSMAP)
    for change in changes:
        if etree.QName(change).namespace != NSMAP["w"]:
            continue
        if not etree.QName(change).localname.endswith("Change"):
            continue
        parent = change.getparent()
        if parent is not None:
            parent.remove(change)
            accepted.property_changes += 1

    for paragraph in emptied_paragraphs:
        if paragraph.getparent() is None:
            continue
        meaningful_children = [child for child in paragraph if child.tag != w("pPr")]
        if meaningful_children:
            continue
        parent = paragraph.getparent()
        if parent is not None:
            parent.remove(paragraph)
            accepted.empty_paragraphs += 1
    return accepted
