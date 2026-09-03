# File Map

## ファイル依存マップ

```
src/docx_redline/
  __init__.py
    - exports: __version__

  errors.py
    - exports: RedlineError
    - used by: text_ops, cli

  ooxml.py
    - imports: (stdlib, lxml)
    - exports: W_NS, NSMAP, w(), qn(), xml_bytes(), utc_timestamp(),
      IdAllocator, next_change_id() (accepts one root or several, e.g. all
      editable_text_parts() roots, so ids stay unique across every part),
      enable_tracking(), set_text(), make_run(), make_tracked_wrapper(),
      make_change(), apply_bold(), RprSignature, rpr_signature()
    - used by: package, text_ops, comments, cleanup, inspect, validate, cli

  package.py
    - imports: ooxml
    - exports: DocxPackage (incl. editable_text_parts(): body + headers/
      footers/footnotes/endnotes, excluding comments.xml)
    - used by: comments, inspect, validate, cli

  text_ops.py
    - imports: errors, ooxml
    - exports: Parts (part-name -> root pairs), find_paragraph(),
      replace_text(), apply_replace_batch(), replace_paragraph_text(),
      insert_paragraph_after(), visible_text()
    - find_paragraph()/replace_text()/apply_replace_batch() accept either a
      single document root or a Parts sequence, searching/editing across
      every part given (see package.editable_text_parts())
    - used by: cli

  comments.py
    - imports: ooxml, package
    - exports: Comment, list_comments(), add_comment(), strip_comments()
    - used by: validate, cli

  cleanup.py
    - imports: errors, ooxml
    - exports: AcceptedRevisions, strip_format_revisions(), accept_revisions()
    - accept_revisions() relocates a comment's commentRangeStart/
      commentRangeEnd/commentReference out of an accepted w:del/w:moveFrom
      when the comment survives elsewhere in the document, so accepting
      never leaves a partial anchor; raises RedlineError if a
      commentReference can't be safely relocated (shares a run with other
      content)
    - used by: cli

  inspect.py
    - imports: ooxml, package
    - exports: ParagraphInfo (incl. part field), inspect_document()
      (single part), inspect_package() (every editable text part,
      globally renumbered)
    - used by: cli

  validate.py
    - imports: comments, ooxml, package
    - exports: CheckResult, ValidationReport, check_zip_integrity(),
      check_tracking_enabled(), check_has_changes(),
      check_no_formatting_insertions(), check_max_deletion_length(),
      check_comments_consistent(), check_paragraph_count(),
      check_protect_numbers(), check_run_properties_preserved(),
      check_contains(), check_not_contains()
    - used by: cli

  word_verify.py
    - imports: errors, ooxml, package (stdlib: subprocess, hashlib, platform,
      shutil)
    - exports: WordVerifyResult, audit_declared_fonts(), verify_word()
    - macOS-only Word automation (via `osascript`) for layout/pagination
      verification, plus a static font-declaration audit (styles.xml +
      document.xml) that needs neither macOS nor Word. All subprocess calls
      go through an injectable `runner` so command construction and error
      handling are unit-testable without Word/macOS - see
      tests/unit/test_word_verify.py
    - used by: cli

  cli.py
    - imports: comments, validate, cleanup, errors, inspect, ooxml,
      package, text_ops, word_verify, typer
    - exports: app, main()
    - entry point: `docx-redline` (pyproject.toml [project.scripts])
```
