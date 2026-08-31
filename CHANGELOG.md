# Changelog

## [Unreleased]

### Added
- `validate`: new `run-properties-preserved` check flags formatting changes on
  text left untouched by tracked changes.

### Changed
- `validate`: `no-bold-insertions` is now `no-formatting-insertions` and also
  covers italic, underline, strike, subscript/superscript, and character
  style inside `w:ins`.

### Fixed
- `replace` / `replace-batch`: a tracked replacement whose match spans runs
  with different formatting (bold, italic, underline, font, character style,
  etc.) is now refused with an error instead of silently applying one run's
  formatting across the whole span. ([#3](https://github.com/y-marui/python-docx-redline/issues/3))
- `rpr_signature`: equivalent ST_OnOff encodings of the same toggle property
  (`<w:b/>`, `w:val="1"`, `"true"`, `"on"`) are now normalized before
  comparison, so they're no longer mistaken for a formatting boundary.
- `validate`: `run-properties-preserved` and other `--original`-diffing
  checks now cover paragraphs nested in tables, not just the document body's
  direct paragraphs.
- `validate`: `run-properties-preserved` no longer risks aligning surviving
  text with the wrong occurrence of a repeated character/phrase; it
  reconstructs each paragraph's original text from the current document's
  own deletions instead of fuzzy-matching against the original.
