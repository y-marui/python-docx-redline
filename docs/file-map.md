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
      IdAllocator, next_change_id(), enable_tracking(), set_text(),
      make_run(), make_tracked_wrapper(), make_change(), apply_bold(),
      RprSignature, rpr_signature()
    - used by: package, text_ops, comments, cleanup, inspect, validate, cli

  package.py
    - imports: ooxml
    - exports: DocxPackage
    - used by: comments, validate, cli

  text_ops.py
    - imports: errors, ooxml
    - exports: visible_text(), find_paragraph(), replace_text(),
      apply_replace_batch(), replace_paragraph_text(),
      insert_paragraph_after()
    - used by: cli

  comments.py
    - imports: ooxml, package
    - exports: Comment, list_comments(), add_comment(), strip_comments()
    - used by: validate, cli

  cleanup.py
    - imports: ooxml
    - exports: strip_format_revisions()
    - used by: cli

  inspect.py
    - imports: ooxml
    - exports: ParagraphInfo, inspect_document()
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
