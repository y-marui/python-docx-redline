"""Clean up or accept existing Word revision markup."""

from __future__ import annotations

from dataclasses import dataclass, field

from lxml import etree

from .errors import RedlineError
from .ooxml import NSMAP, w

_COMMENT_ANCHOR_TAGS = ("commentRangeStart", "commentRangeEnd", "commentReference")


@dataclass
class AcceptedRevisions:
    """Counts of revision nodes accepted from one WordprocessingML part.

    `removed_comment_ids` collects ids of comments whose entire anchor was
    accepted away together (the whole comment, not just an endpoint) -
    candidates for the caller to also drop from word/comments.xml, once
    confirmed orphaned across every processed part.
    """

    insertions: int = 0
    deletions: int = 0
    property_changes: int = 0
    empty_paragraphs: int = 0
    removed_comment_ids: set[str] = field(default_factory=set)

    def add(self, other: AcceptedRevisions) -> None:
        """Add counts from another processed part."""
        self.insertions += other.insertions
        self.deletions += other.deletions
        self.property_changes += other.property_changes
        self.empty_paragraphs += other.empty_paragraphs
        self.removed_comment_ids |= other.removed_comment_ids


def strip_format_revisions(document: etree._Element) -> int:
    """Remove w:pPrChange markers (paragraph-formatting revision history)."""
    changes = document.xpath(".//w:pPrChange", namespaces=NSMAP)
    for change in changes:
        parent = change.getparent()
        if parent is not None:
            parent.remove(change)
    return len(changes)


def _is_inside(node: etree._Element, ancestor: etree._Element) -> bool:
    while node is not None:
        if node is ancestor:
            return True
        node = node.getparent()
    return False


def _survives_outside(
    document: etree._Element, tag: str, comment_id: str | None, deletion: etree._Element
) -> bool:
    """Whether a `w:<tag>` for `comment_id` exists anywhere outside `deletion`."""
    matches = document.xpath(f".//w:{tag}[@w:id=$id]", namespaces=NSMAP, id=comment_id)
    return any(not _is_inside(match, deletion) for match in matches)


def _comment_relocation_node(anchor: etree._Element) -> etree._Element:
    """The element to actually move for `anchor`.

    `commentRangeStart`/`commentRangeEnd` move as themselves, but OOXML
    requires a `commentReference` to live inside a `w:r`, so that run moves
    as a whole. Raises if the run carries anything beyond the reference and
    its `w:rPr` - splitting that safely isn't implemented.
    """
    if etree.QName(anchor).localname != "commentReference":
        return anchor
    run = anchor.getparent()
    if run is None or run.tag != w("r"):
        return anchor
    extra = [child for child in run if child is not anchor and child.tag != w("rPr")]
    if extra:
        raise RedlineError(
            f"cannot accept revisions: commentReference {anchor.get(w('id'))} "
            "shares a run with other content, so it cannot be safely "
            "relocated out of an accepted deletion"
        )
    return run


def _relocate_comment_anchors(
    document: etree._Element, deletion: etree._Element
) -> set[str]:
    """Move comment anchors out of `deletion` before it is discarded.

    A comment id with no surviving anchor occurrence anywhere else in the
    document is left untouched - the whole comment is being removed
    together, which stays internally consistent - and returned to the
    caller as a candidate to also drop from word/comments.xml. Otherwise,
    each anchor *kind* (`commentRangeStart`/`commentRangeEnd`/
    `commentReference`) that would otherwise vanish entirely is relocated to
    the position `deletion` currently occupies; a kind that already survives
    elsewhere (e.g. duplicated across a w:moveFrom/w:moveTo pair) is simply
    dropped rather than relocated into a duplicate.
    """
    anchors = deletion.xpath(
        " | ".join(f".//w:{tag}" for tag in _COMMENT_ANCHOR_TAGS), namespaces=NSMAP
    )
    if not anchors:
        return set()
    ids = {anchor.get(w("id")) for anchor in anchors}
    ids_with_survivor = {
        comment_id
        for comment_id in ids
        if any(
            _survives_outside(document, tag, comment_id, deletion)
            for tag in _COMMENT_ANCHOR_TAGS
        )
    }
    to_relocate = [
        anchor
        for anchor in anchors
        if anchor.get(w("id")) in ids_with_survivor
        and not _survives_outside(
            document, etree.QName(anchor).localname, anchor.get(w("id")), deletion
        )
    ]
    if to_relocate:
        parent = deletion.getparent()
        if parent is None:
            raise RedlineError(
                "cannot accept revisions: a deletion holding a comment "
                "anchor has no parent to relocate it to"
            )
        index = parent.index(deletion)
        moved: list[etree._Element] = []
        for anchor in to_relocate:
            node = _comment_relocation_node(anchor)
            if node in moved:
                continue
            moved.append(node)
            current_parent = node.getparent()
            if current_parent is not None:
                current_parent.remove(node)
            parent.insert(index, node)
            index += 1
    return ids - ids_with_survivor


def accept_revisions(document: etree._Element) -> AcceptedRevisions:
    """Accept text, move, and property revisions in one WordprocessingML tree."""
    accepted = AcceptedRevisions()
    emptied_paragraphs: list[etree._Element] = []
    for deletion in document.xpath(".//w:del | .//w:moveFrom", namespaces=NSMAP):
        accepted.removed_comment_ids |= _relocate_comment_anchors(document, deletion)
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
