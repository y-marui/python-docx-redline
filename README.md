# docx-redline

> **This is the reference (English) version.**
> The canonical (Japanese) version is [README-jp.md](README-jp.md).

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/y-marui/python-docx-redline/actions/workflows/ci.yml/badge.svg)](https://github.com/y-marui/python-docx-redline/actions/workflows/ci.yml)
[![Charter Check](https://github.com/y-marui/python-docx-redline/actions/workflows/dev-charter-check.yml/badge.svg)](https://github.com/y-marui/python-docx-redline/actions/workflows/dev-charter-check.yml)

A command-line tool for editing Word (`.docx`) documents as safe, minimal
tracked changes (Track Changes) — without writing a one-off script each time.

This replaces a pattern of hand-rolled, throwaway Python scripts that poked at
raw OOXML with `lxml` during every proofreading pass. Every edit here:

- never touches the input file (writes to a separate `--out` path)
- lands as a real Word revision (`w:ins` / `w:del`) that a reviewer can accept
  or reject in Word normally
- splits cleanly across run boundaries without corrupting surrounding
  formatting, fields, or bookmarks
- refuses to guess: if the target text isn't uniquely identified, it errors
  out instead of silently editing the wrong spot

## Setup

```sh
git clone https://github.com/y-marui/python-docx-redline.git
cd python-docx-redline
make install
```

Once built, install it as a standalone command from any other project with
`uv tool install --from git+https://github.com/y-marui/python-docx-redline docx-redline`.

## Commands

| Command | Purpose |
|---|---|
| `inspect` | Dump each paragraph's style, page/section breaks, ins/del counts, and revision-aware text |
| `list-comments` | List existing Word comments (id, author, date, text) |
| `replace` | Replace text as a minimal tracked change (del+ins) |
| `replace-batch` | Apply a sequential list of replacements from a JSON file (replaces the old throwaway scripts) |
| `replace-paragraph` | Replace an entire paragraph's text as a tracked change |
| `insert-paragraph` | Insert a new paragraph, tracked as an insertion, after an anchor paragraph |
| `add-comment` | Anchor a Word comment to a paragraph (creates `comments.xml` plumbing as needed) |
| `strip-comments` | Remove every comment and its anchors |
| `strip-format-revisions` | Remove formatting-only revisions (`w:pPrChange`) that clutter the diff |
| `accept-revisions` | Write a separate copy with all existing revisions accepted |
| `enable-tracking` | Turn on Track Changes |
| `validate` | Pre-delivery safety checks (see below) |

### `replace`: exactly one match by default

```sh
docx-redline replace draft.docx "old phrasing" "new phrasing" --out draft-fix1.docx --author "Review Agent"
```

If more than one match exists, the command errors out instead of guessing —
this is the safety net against silently editing the wrong occurrence. Pass
`--occurrence N` to pick one by index, or `--all` to replace every match.
`--paragraph-contains TEXT` scopes the search to matching paragraphs.

### `replace-batch`: apply a sequence of edits in one pass

```json
[
  { "old": "some phrase", "new": "a better phrase" },
  { "old": "another phrase", "new": "its replacement" }
]
```

```sh
docx-redline replace-batch draft.docx --pairs pairs.json --out draft-fix1.docx --author "Review Agent"
```

Each entry may also set `all` / `occurrence` / `bold` / `paragraph_contains`,
matching the same-named `replace` options.

### `accept-revisions`: create a review copy with existing revisions accepted

```sh
docx-redline accept-revisions draft.docx --out draft-accepted.docx
```

The input remains unchanged. The command accepts existing insertions, deletions,
moves, and property revisions in WordprocessingML parts such as the document
body, headers, footers, and notes. It retains comments and unrelated package
parts, then reports the accepted-change and empty-paragraph counts.

### Authorship

Every command that creates tracked revisions or comments requires `--author`.
Pass the actual name of the person or code agent performing the review; the
tool does not invent a generic reviewer identity.

### `validate`: pre-delivery safety checks

```sh
docx-redline validate draft-fix1.docx --original draft.docx --max-deletion-length 60
```

Checks include: zip integrity, Track Changes enabled, changes actually
present (`--no-require-changes` to skip), no notable formatting (bold,
italic, underline, strike, subscript/superscript, character style) on
inserted text, comment anchors all present and matched, and — when
`--original` is given — paragraph count unchanged, numbers/units (via
`--number-pattern`) preserved, and formatting on untouched text unchanged.
`--contains` / `--not-contains` (repeatable) assert specific fragments
survived or were removed. Any failing check exits with status 1.

## Usage

```sh
make all    # lint + type + test
```

| Command | Description |
|---|---|
| `make install` | `uv sync` |
| `make lint` | `ruff check .` |
| `make type` | `mypy src` |
| `make test` | `pytest` |
| `make all` | lint + type + test |

## Known limitations (v1)

- Editing targets `word/document.xml` (the body) only; header/footer body
  text isn't a `replace` target (though `strip-comments` does clean up
  comments in headers/footers too)
- Table paragraphs are valid `replace` targets, but table structure itself
  (adding/removing rows or columns) isn't handled
- Replacements can't safely cross math objects (OMML), content controls, or
  fields — the command errors out rather than risk corrupting them

## License

MIT License — see [LICENSE](LICENSE)

---
*This document has a Japanese canonical version [README-jp.md](README-jp.md). Update both in the same commit when editing.*
