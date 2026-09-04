# Changelog

## [Unreleased]

### Added
- `--version`/`-V` flag prints the installed version and exits. Shell
  completion is also available via the existing typer-provided
  `--install-completion`/`--show-completion` flags (see README).
- New `export-pdf` command (macOS only): converts a `.docx` to PDF via the same
  Microsoft Word automation `verify-word` uses, without the layout/font
  verification overhead. Defaults to writing next to the input with its
  extension replaced by `.pdf`; `--output` picks another path. Refuses to
  overwrite an existing output file.
- `validate`: new `run-properties-preserved` check flags formatting changes on
  text left untouched by tracked changes.
- New `verify-word` command (macOS only): opens the input `.docx` read-only
  through Microsoft Word automation, repaginates it, exports a verification
  PDF, and reports the Word version, page count, and PDF SHA-256 as JSON
  (`--json`) or text. `--png-dir` optionally rasterizes each PDF page (via
  `pdftoppm`/poppler). Also audits fonts declared in `word/styles.xml` and
  `word/document.xml`'s `w:rFonts`, with `--required-font` (must be declared
  somewhere) and `--expected-font` (only these may be declared) options;
  either exits non-zero with an actionable message. LibreOffice is
  deliberately not used as a fallback renderer.
  ([#10](https://github.com/y-marui/python-docx-redline/issues/10))
- `replace` / `replace-batch`: `--before`/`--after` (`before`/`after` per pair)
  narrow a match to one with specific surrounding text, without that context
  ever becoming part of the tracked change.
- `replace-batch`: `as_literal` per pair opts a pair out of the new
  minimal-diff default (see below), deleting all of `old` and inserting all
  of `new` verbatim instead. ([#11](https://github.com/y-marui/python-docx-redline/issues/11))
- `inspect`, `replace`, `replace-batch`, `replace-paragraph`, and
  `insert-paragraph` now cover every editable text part - the main document
  plus headers, footers, footnotes, and endnotes - not just
  `word/document.xml`. `inspect --json` reports a `part` field per paragraph;
  `replace`/`replace-paragraph`/`insert-paragraph` take `--part` and
  `replace-batch` pairs take `"part"` to restrict a search to one named part,
  as reported by `inspect --json`. A target ambiguous across parts is refused
  unless narrowed this way. `word/comments.xml` is intentionally out of
  scope - it has its own `add-comment`/`list-comments` surface.
  ([#13](https://github.com/y-marui/python-docx-redline/issues/13))

### Changed
- `validate`: `no-bold-insertions` is now `no-formatting-insertions` and also
  covers italic, underline, strike, subscript/superscript, and character
  style inside `w:ins`.
- `replace` / `replace-batch`: `old`/`new` may now be full sentences; by
  default only their differing middle span (common prefix/suffix trimmed) is
  recorded as the tracked change, instead of deleting and reinserting the
  whole match. Pass `--as-literal` (`replace`) or `as_literal: true` (a
  `replace-batch` pair) to keep the previous whole-string behavior.
  ([#11](https://github.com/y-marui/python-docx-redline/issues/11))
- `replace-batch`: every pair's target is now resolved against the input
  document before any pair is applied, so an earlier pair's edit can no
  longer shift where a later pair's `occurrence` resolves to. Pairs whose
  resolved spans overlap fail the whole batch before anything is written.
  ([#11](https://github.com/y-marui/python-docx-redline/issues/11))
- `replace` / `replace-batch`: a deletion-only edit (empty `new`) may now
  span runs with different formatting, preserving each deleted run's own
  properties; a replacement that would still need to pick one formatting
  policy across mismatched runs continues to be refused.
  ([#11](https://github.com/y-marui/python-docx-redline/issues/11))

### Fixed
- `validate`: `no-formatting-insertions` no longer flags an insertion whose
  run properties exactly match the `w:del` it immediately replaces - a
  formatting-preserving edit, not a newly introduced one. An insertion that
  introduces formatting the source didn't have (or that follows a deletion
  spanning more than one formatting signature, so there's no single source
  to compare against) is still flagged.
  ([#12](https://github.com/y-marui/python-docx-redline/issues/12))
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
- `accept-revisions`: no longer silently leaves a Word comment with a partial
  anchor (some but not all of `commentRangeStart`/`commentRangeEnd`/
  `commentReference`) when accepting a `w:del`/`w:moveFrom` that contains one
  but not all of a comment's anchor elements - each anchor kind that would
  otherwise vanish is relocated to the accepted deletion's position instead
  of being discarded with it, while a kind already surviving elsewhere (e.g.
  duplicated across a `w:moveFrom`/`w:moveTo` pair) is dropped rather than
  duplicated. Refuses to write output (with the comment id in the error) for
  the one case that can't be relocated safely: a `commentReference` sharing
  a run with other content. A deletion that contains an entire comment's
  anchor still removes it as before, and now also drops the comment's now-
  orphaned `word/comments.xml` entry once confirmed unanchored anywhere else
  in the package. ([#22](https://github.com/y-marui/python-docx-redline/issues/22))
