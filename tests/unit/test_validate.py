from __future__ import annotations

from docx_redline import comments as comments_mod
from docx_redline import validate as validate_mod
from docx_redline.ooxml import NSMAP, enable_tracking, next_change_id, utc_timestamp
from docx_redline.package import DocxPackage
from docx_redline.text_ops import find_paragraph, replace_paragraph_text, replace_text


def test_check_zip_integrity_passes_for_valid_docx(docx_factory) -> None:
    docx = docx_factory("doc.docx", [["Text."]])
    report = validate_mod.ValidationReport()
    validate_mod.check_zip_integrity(docx, report)
    assert report.ok


def test_check_tracking_enabled_reflects_settings(docx_factory) -> None:
    docx = docx_factory("doc.docx", [["Text."]])
    package = DocxPackage(docx)
    report = validate_mod.ValidationReport()
    validate_mod.check_tracking_enabled(package, report)
    assert not report.ok

    enable_tracking(package.xml("word/settings.xml"))
    report2 = validate_mod.ValidationReport()
    validate_mod.check_tracking_enabled(package, report2)
    assert report2.ok


def test_check_no_bold_insertions_flags_bold_run(docx_factory) -> None:
    docx = docx_factory("doc.docx", [["Hello world."]])
    package = DocxPackage(docx)
    document = package.xml("word/document.xml")
    ids = next_change_id(document)
    replace_text(document, "world", "there", ids, "Tester", utc_timestamp(), bold=True)

    report = validate_mod.ValidationReport()
    validate_mod.check_no_bold_insertions(document, report)
    assert not report.ok


def test_check_max_deletion_length_flags_long_deletion(docx_factory) -> None:
    docx = docx_factory("doc.docx", [["A very long sentence to delete entirely now."]])
    package = DocxPackage(docx)
    document = package.xml("word/document.xml")
    ids = next_change_id(document)
    paragraph = document.xpath(".//w:p", namespaces=NSMAP)[0]
    replace_paragraph_text(paragraph, "Short.", ids, "Tester", utc_timestamp())

    report = validate_mod.ValidationReport()
    validate_mod.check_max_deletion_length(document, report, 10)
    assert not report.ok


def test_check_protect_numbers_detects_changed_number(docx_factory) -> None:
    original_docx = docx_factory("original.docx", [["Value is 42 nm."]])
    edited_docx = docx_factory("edited.docx", [["Value is 43 nm."]])
    original = DocxPackage(original_docx).xml("word/document.xml")
    edited = DocxPackage(edited_docx).xml("word/document.xml")

    report = validate_mod.ValidationReport()
    validate_mod.check_protect_numbers(edited, original, r"\d+", report)
    assert not report.ok


def test_check_comments_consistent_passes_for_well_formed_comment(docx_factory) -> None:
    docx = docx_factory("doc.docx", [["Please review this."]])
    package = DocxPackage(docx)
    document = package.xml("word/document.xml")
    paragraph = find_paragraph(document, contains="review")
    comments_mod.add_comment(
        package, paragraph, "note", author="Tester", when=utc_timestamp()
    )

    report = validate_mod.ValidationReport()
    validate_mod.check_comments_consistent(package, document, report)
    assert report.ok


def test_check_comments_consistent_fails_when_anchor_missing(docx_factory) -> None:
    docx = docx_factory("doc.docx", [["Please review this."]])
    package = DocxPackage(docx)
    document = package.xml("word/document.xml")
    paragraph = find_paragraph(document, contains="review")
    comments_mod.add_comment(
        package, paragraph, "note", author="Tester", when=utc_timestamp()
    )
    for element in document.xpath(".//w:commentRangeEnd", namespaces=NSMAP):
        element.getparent().remove(element)

    report = validate_mod.ValidationReport()
    validate_mod.check_comments_consistent(package, document, report)
    assert not report.ok


def test_check_contains_and_not_contains(docx_factory) -> None:
    docx = docx_factory("doc.docx", [["Keep this phrase."]])
    package = DocxPackage(docx)
    document = package.xml("word/document.xml")

    report = validate_mod.ValidationReport()
    validate_mod.check_contains(document, ["Keep this"], report)
    validate_mod.check_not_contains(document, ["Forbidden"], report)
    assert report.ok

    report2 = validate_mod.ValidationReport()
    validate_mod.check_contains(document, ["Missing"], report2)
    assert not report2.ok
