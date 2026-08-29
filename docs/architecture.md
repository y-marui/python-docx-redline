# Architecture

## Layers

```
cli.py                  typer subcommands; opens/saves DocxPackage, prints reports
  |
  v
text_ops / comments /    pure functions operating on lxml elements already
cleanup / inspect /       loaded from a DocxPackage; no I/O of their own
validate
  |
  v
package.py               DocxPackage: read/write a .docx zip, part by part,
                          lazily parsing/serializing only touched parts
  |
  v
ooxml.py                 namespaces, w:ins/w:del/w:r construction, id
                          allocation, tracked-change timestamp formatting
```

`ooxml.py` has no dependency on any other module in this package. Everything
else depends downward only; no module below `cli.py` imports `typer`.

## Editing model: minimal tracked replacement

The core problem this tool solves is textbook find/replace, except a Word
run (`<w:r><w:t>...</w:t></w:r>`) rarely lines up with the text a human wants
to replace — the target string can start mid-run, end mid-run, or span
several runs with different formatting. `text_ops.py` handles this by:

1. Splitting each paragraph into maximal *segments* of consecutive plain
   `<w:r><w:t>` siblings (`w:proofErr` is skipped, anything else — a
   drawing, a field, an existing `w:ins`/`w:del` — ends the segment). This is
   also what keeps existing tracked changes untouched: they live one level
   deeper than the paragraph's direct children, so a segment never includes
   text already inside a revision.
2. Searching each segment's concatenated text for the target string.
3. On a match, mapping the match's [start, end) offset back onto the
   contributing runs, splitting the first/last run into an untouched
   "before"/"after" fragment plus the matched middle, and replacing the
   matched middle with a `w:del` wrapper (preserving each source run's
   `w:rPr`) followed by a `w:ins` wrapper (using the first run's `w:rPr`,
   optionally forcing bold via `apply_bold`).

`replace_text()` wraps this with the safety policy: by default there must be
exactly one match in the whole document, or the call raises `RedlineError`
rather than guess. Multiple matches require an explicit `--occurrence` index
or `--all`. After each single application it rescans (rather than trying to
track stale offsets), which keeps the algorithm simple at the cost of O(n^2)
behavior — fine at proofreading-document scale.

## Package part handling

`DocxPackage` keeps the original `zipfile.ZipInfo` list so `save()` can
round-trip untouched parts byte-for-byte (preserving compression settings)
while only re-serializing parts that were actually loaded via `.xml()` and
mutated. New parts (e.g. `word/comments.xml` when a document had none) are
tracked separately and appended on save; deleted parts are dropped. `save()`
refuses to write back to the input path — every command takes a required
`--out`.

## Known limitations (see README for the user-facing list)

- Only `word/document.xml` is a `replace`/`replace-paragraph`/
  `insert-paragraph` target; headers/footers are only touched by
  `strip-comments`.
- No math (OMML), content-control, or field-aware splitting — a replacement
  that would need to cross one of these safely fails instead.
