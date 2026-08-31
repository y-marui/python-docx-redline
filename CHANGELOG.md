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
