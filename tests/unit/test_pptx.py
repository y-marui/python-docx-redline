from copy import deepcopy

import pytest

from docx_redline.errors import RedlineError
from docx_redline.package import DocxPackage
from docx_redline.pptx import NS, child, find_target, qn, slides, text_targets
from docx_redline.pptx_comments import add_comment, apply_batch, list_comments
from docx_redline.pptx_validate import validate


def test_find_target_run_boundaries_unicode_and_slide_order(pptx_path):
    pkg = DocxPackage(pptx_path)
    target = find_target(pkg, "Autum")
    assert target.slide.number == 1
    assert target.slide.part.endswith("slide7.xml")
    assert target.start == 5  # Japanese (2), surrogate pair (2), space (1).
    assert target.length == 5
    second = find_target(pkg, "Second paragraph", slide=1)
    assert second.start == 24
    assert text_targets(slides(pkg)[0])[0].text == (
        "日本😀 Autum meeting\vsoft\rSecond paragraph"
    )


@pytest.mark.parametrize(
    "match,kwargs",
    [
        ("", {}),
        ("missing", {}),
        ("Duplicate", {}),
        ("Duplicate", {"occurrence": 0}),
        ("Duplicate", {"occurrence": 4}),
        ("Autum", {"slide": 3}),
        ("Autum", {"shape_id": "missing"}),
    ],
)
def test_find_target_invalid_or_ambiguous_raises(pptx_path, match, kwargs):
    with pytest.raises(RedlineError):
        find_target(DocxPackage(pptx_path), match, **kwargs)


def test_find_target_explicit_occurrence(pptx_path):
    target = find_target(DocxPackage(pptx_path), "Duplicate", occurrence=2)
    assert target.start == 10


def test_add_comment_roundtrip_exact_anchor_and_preservation(pptx_path, tmp_path):
    pkg = DocxPackage(pptx_path)
    comment_id = add_comment(
        pkg, "Use Autumn <&>\n提案", author="Reviewer", match="Autum"
    )
    out = tmp_path / "review.pptx"
    pkg.save(out)
    saved = DocxPackage(out)
    assert validate(saved, DocxPackage(pptx_path)) == 1
    comment = list_comments(saved)[0]
    assert comment["id"] == comment_id
    assert (comment["shape_id"], comment["start"], comment["length"]) == ("4", 5, 5)
    assert comment["text"] == "Use Autumn <&>\n提案"
    root = saved.xml(str(comment["part"]))
    anchor = root.find("p188:cm/ac:txMkLst", NS)
    assert [n.tag for n in anchor] == [
        qn("pc:docMk"),
        qn("pc:sldMk"),
        qn("ac:spMk"),
        qn("ac:txMk"),
    ]
    assert anchor.find("pc:sldMk", NS).get("sldId") == "256"
    assert saved.raw("ppt/media/image.png") == b"unchanged binary"
    assert (
        saved.raw("ppt/notesSlides/notesSlide1.xml") == b"<notes>unchanged memo</notes>"
    )
    assert saved.raw("ppt/slides/slide2.xml") == DocxPackage(pptx_path).raw(
        "ppt/slides/slide2.xml"
    )


def test_add_comment_append_preserves_previous_comments(pptx_path, tmp_path):
    pkg = DocxPackage(pptx_path)
    add_comment(pkg, "First", author="Reviewer", match="Autum")
    first = tmp_path / "first.pptx"
    pkg.save(first)
    pkg = DocxPackage(first)
    add_comment(pkg, "Second", author="Reviewer", match="meeting")
    add_comment(pkg, "Whole-slide feedback", author="Other", slide=2, slide_level=True)
    second = tmp_path / "second.pptx"
    pkg.save(second)
    saved = DocxPackage(second)
    assert validate(saved, DocxPackage(first)) == 3
    assert [c["text"] for c in list_comments(saved)] == [
        "First",
        "Second",
        "Whole-slide feedback",
    ]
    assert len(saved.xml("ppt/authors.xml")) == 2


@pytest.mark.parametrize(
    "entry",
    [
        {},
        {"text": "a", "match": ""},
        {"text": "a", "slide": True},
        {"text": "a", "match": "Autum", "unknown": 1},
        {"text": "a", "slide": 1, "slide_level": "yes"},
        {"text": "a", "slide": 1, "slide_level": True, "match": "Autum"},
        {"text": "a", "slide": 3, "slide_level": True},
    ],
)
def test_batch_invalid_entry_raises(pptx_path, entry):
    with pytest.raises(RedlineError):
        apply_batch(DocxPackage(pptx_path), [entry], author="Reviewer")


def test_validate_invalid_range_raises(pptx_path):
    pkg = DocxPackage(pptx_path)
    add_comment(pkg, "a", author="Reviewer", match="Autum")
    part = str(list_comments(pkg)[0]["part"])
    pkg.xml(part).find(".//ac:txMk", NS).set("cp", "9999")
    with pytest.raises(RedlineError, match="out of bounds"):
        validate(pkg)


def test_validate_changed_slide_raises(pptx_path, tmp_path):
    pkg = DocxPackage(pptx_path)
    add_comment(pkg, "a", author="Reviewer", match="Autum")
    slides(pkg)[0].root.find(".//a:t", NS).text = "Different text"
    out = tmp_path / "changed.pptx"
    pkg.save(out)
    with pytest.raises(RedlineError, match="Slide content changed"):
        validate(DocxPackage(out), DocxPackage(pptx_path))


def test_grouped_text_not_silently_anchored(pptx_path):
    pkg = DocxPackage(pptx_path)
    tree = slides(pkg)[0].root.find("p:cSld/p:spTree", NS)
    shape = tree.find("p:sp", NS)
    group = child(tree, "p:grpSp")
    group.append(shape)
    with pytest.raises(RedlineError, match="not found"):
        find_target(pkg, "Autum")


def test_unsupported_paragraph_content_still_excludes_shape(pptx_path):
    pkg = DocxPackage(pptx_path)
    slide = slides(pkg)[0]
    shape = slide.root.find("p:cSld/p:spTree/p:sp", NS)
    child(shape.find("p:txBody/a:p", NS), "a:fakeUnsupported")
    assert not any(t.shape_id == "4" for t in text_targets(slide))
    with pytest.raises(RedlineError, match="not found"):
        find_target(pkg, "Autum")


def test_equation_shape_in_alternate_content_choice_is_anchorable(pptx_path, tmp_path):
    """PowerPoint wraps a shape holding an inserted equation (a14:m) in
    mc:AlternateContent instead of placing it directly under spTree; the
    equation itself becomes an opaque placeholder so surrounding plain text
    (e.g. "elementary charge") stays anchorable."""
    pkg = DocxPackage(pptx_path)
    slide = slides(pkg)[0]
    tree = slide.root.find("p:cSld/p:spTree", NS)
    alt = child(tree, "mc:AlternateContent")
    choice = child(alt, "mc:Choice", Requires="a14")
    shape = child(choice, "p:sp")
    child(child(shape, "p:nvSpPr"), "p:cNvPr", id="50", name="Equation")
    body = child(shape, "p:txBody")
    child(body, "a:bodyPr")
    child(body, "a:lstStyle")
    para = child(body, "a:p")
    child(child(para, "a:r"), "a:t").text = "e: elementary charge, "
    child(para, "a14:m")
    child(child(para, "a:r"), "a:t").text = "ℏ: Dirac constant"
    fallback_shape = child(child(alt, "mc:Fallback"), "p:sp")
    child(child(fallback_shape, "p:nvSpPr"), "p:cNvPr", id="51", name="Fallback")

    equation = next(t for t in text_targets(slide) if t.shape_id == "50")
    assert equation.text == "e: elementary charge, ￼ℏ: Dirac constant"
    assert not any(t.shape_id == "51" for t in text_targets(slide))

    source = tmp_path / "equation.pptx"
    pkg.save(source)
    pkg = DocxPackage(source)
    add_comment(pkg, "Confirm symbol", author="Reviewer", match="Dirac constant")
    out = tmp_path / "equation-comment.pptx"
    pkg.save(out)
    assert validate(DocxPackage(out), DocxPackage(source)) == 1


def test_alternate_content_fallback_used_when_no_choice(pptx_path):
    pkg = DocxPackage(pptx_path)
    slide = slides(pkg)[0]
    tree = slide.root.find("p:cSld/p:spTree", NS)
    alt = child(tree, "mc:AlternateContent")
    shape = child(child(alt, "mc:Fallback"), "p:sp")
    child(child(shape, "p:nvSpPr"), "p:cNvPr", id="52", name="Fallback only")
    body = child(shape, "p:txBody")
    child(body, "a:bodyPr")
    child(body, "a:lstStyle")
    child(child(child(body, "a:p"), "a:r"), "a:t").text = "Fallback text"

    found = next(t for t in text_targets(slide) if t.shape_id == "52")
    assert found.text == "Fallback text"


def test_alternate_content_picture_is_commentable(pptx_path, tmp_path):
    pkg = DocxPackage(pptx_path)
    tree = slides(pkg)[0].root.find("p:cSld/p:spTree", NS)
    choice = child(child(tree, "mc:AlternateContent"), "mc:Choice", Requires="a14")
    picture = child(choice, "p:pic")
    child(child(picture, "p:nvPicPr"), "p:cNvPr", id="60", name="Diagram")
    source = tmp_path / "alt-picture.pptx"
    pkg.save(source)

    pkg = DocxPackage(source)
    add_comment(pkg, "Check figure", author="Reviewer", slide=1, object_id="60")
    out = tmp_path / "alt-picture-comment.pptx"
    pkg.save(out)
    assert validate(DocxPackage(out), DocxPackage(source)) == 1


def test_duplicate_shape_id_fails_validation(pptx_path):
    pkg = DocxPackage(pptx_path)
    tree = slides(pkg)[0].root.find("p:cSld/p:spTree", NS)
    shape = deepcopy(tree.find("p:sp", NS))
    shape.find(".//a:t", NS).text = "other"
    tree.append(shape)
    add_comment(pkg, "a", author="Reviewer", match="Autum", occurrence=1)
    with pytest.raises(RedlineError, match="ambiguous comment shape"):
        validate(pkg)


def test_classic_comment_preserved_when_adding_modern(pptx_path, tmp_path):
    from lxml import etree

    pkg = DocxPackage(pptx_path)
    rels = etree.Element(qn("rel:Relationships"), nsmap={None: NS["rel"]})
    child(
        rels,
        "rel:Relationship",
        Id="rId1",
        Type=NS["r"] + "/comments",
        Target="../comments/legacy.xml",
    )
    pkg.new_xml("ppt/slides/_rels/slide7.xml.rels", rels)
    root = etree.Element(qn("p:cmLst"), nsmap=NS)
    cm = child(root, "p:cm", authorId="0", idx="1")
    child(cm, "p:pos", x="10", y="20")
    child(cm, "p:text").text = "Existing review"
    pkg.new_xml("ppt/comments/legacy.xml", root)
    source = tmp_path / "classic.pptx"
    pkg.save(source)
    pkg = DocxPackage(source)
    add_comment(pkg, "New review", author="Reviewer", match="Autum")
    out = tmp_path / "mixed.pptx"
    pkg.save(out)
    saved = DocxPackage(out)
    assert validate(saved, DocxPackage(source)) == 1
    assert [c["text"] for c in list_comments(saved)] == [
        "Existing review",
        "New review",
    ]
    assert saved.raw("ppt/comments/legacy.xml") == DocxPackage(source).raw(
        "ppt/comments/legacy.xml"
    )


def test_validate_missing_content_type_raises(pptx_path):
    pkg = DocxPackage(pptx_path)
    add_comment(pkg, "a", author="Reviewer", match="Autum")
    types = pkg.xml("[Content_Types].xml")
    for node in list(types):
        if node.get("PartName") == "/ppt/authors.xml":
            types.remove(node)
    with pytest.raises(RedlineError, match="content type"):
        validate(pkg)


def test_picture_object_comment_roundtrip(pptx_path, tmp_path):
    pkg = DocxPackage(pptx_path)
    slide = slides(pkg)[0]
    tree = slide.root.find("p:cSld/p:spTree", NS)
    picture = child(tree, "p:pic")
    props = child(child(picture, "p:nvPicPr"), "p:cNvPr", id="12", name="Diagram")
    ext = child(child(props, "a:extLst"), "a:ext", uri="{PICTURE-CREATION}")
    creation_id = "{A392048A-87BE-8C7C-34E0-52A5263DF56F}"
    child(ext, "a16:creationId", id=creation_id)
    source = tmp_path / "picture.pptx"
    pkg.save(source)

    pkg = DocxPackage(source)
    add_comment(pkg, "Fix image wording", author="Reviewer", slide=1, object_id="12")
    out = tmp_path / "picture-comment.pptx"
    pkg.save(out)
    saved = DocxPackage(out)
    assert validate(saved, DocxPackage(source)) == 1
    comment = list_comments(saved)[0]
    assert (comment["object_id"], comment["object_kind"]) == ("12", "picMk")
    anchor = saved.xml(str(comment["part"])).find("p188:cm/ac:deMkLst", NS)
    assert anchor.find("ac:picMk", NS).get("creationId") == creation_id


def test_empty_shape_object_comment(pptx_path):
    pkg = DocxPackage(pptx_path)
    add_comment(pkg, "Fill this box", author="Reviewer", slide=1, object_id="4")
    assert validate(pkg) == 1
    comment = list_comments(pkg)[0]
    assert (comment["object_id"], comment["object_kind"]) == ("4", "spMk")


def test_object_comment_requires_unique_object_and_slide(pptx_path):
    with pytest.raises(RedlineError, match="requires a slide"):
        add_comment(
            DocxPackage(pptx_path),
            "fix",
            author="Reviewer",
            object_id="4",
        )
    with pytest.raises(RedlineError, match="missing or ambiguous"):
        add_comment(
            DocxPackage(pptx_path),
            "fix",
            author="Reviewer",
            slide=1,
            object_id="999",
        )


def test_anchor_existing_creation_ids_preserved(pptx_path, tmp_path):
    pkg = DocxPackage(pptx_path)
    slide = slides(pkg)[0]
    ext = child(slide.root.find("p:extLst", NS), "p:ext", uri="{SLIDE-CREATION}")
    child(ext, "p14:creationId", val="131243585")
    props = slide.root.find("p:cSld/p:spTree/p:sp/p:nvSpPr/p:cNvPr", NS)
    ext = child(child(props, "a:extLst"), "a:ext", uri="{SHAPE-CREATION}")
    creation_id = "{47CBDB37-82C9-A8C5-CE3A-0DB6ABA45FB7}"
    child(ext, "a16:creationId", id=creation_id)
    source = tmp_path / "creation-ids.pptx"
    pkg.save(source)
    pkg = DocxPackage(source)
    add_comment(pkg, "fix", author="Reviewer", match="Autum")
    part = str(list_comments(pkg)[0]["part"])
    anchor = pkg.xml(part).find("p188:cm/ac:txMkLst", NS)
    assert anchor.find("pc:sldMk", NS).get("cId") == "131243585"
    assert anchor.find("ac:spMk", NS).get("creationId") == creation_id
    out = tmp_path / "anchored.pptx"
    pkg.save(out)
    assert validate(DocxPackage(out), DocxPackage(source)) == 1
    anchor.find("pc:sldMk", NS).attrib.pop("cId")
    with pytest.raises(RedlineError, match="slide creation ID"):
        validate(pkg)
    anchor.find("pc:sldMk", NS).set("cId", "131243585")
    anchor.find("ac:spMk", NS).attrib.pop("creationId")
    with pytest.raises(RedlineError, match="shape creation ID"):
        validate(pkg)
