# Specification

See [README.md](../README.md) for the command reference and human-facing
usage. This document specifies the machine-readable contracts other tools or
scripts can rely on.

## `replace-batch` pairs file (`--pairs`)

A JSON array of objects. Only `old` and `new` are required; the rest default
to the same values as the `replace` command's flags:

```json
[
  {
    "old": "string, required, non-empty",
    "new": "string, required (empty string deletes with no replacement)",
    "all": false,
    "occurrence": null,
    "bold": null,
    "paragraph_contains": null
  }
]
```

Pairs are applied in array order, against the same in-memory document, using
one shared `IdAllocator` and one shared timestamp for all resulting
`w:ins`/`w:del` elements. If any pair fails (ambiguous match, not found, or
an out-of-range `occurrence`), the command exits with status 1 and no file
is written — the whole batch is all-or-nothing.

## `inspect --json`

A JSON array of objects, one per paragraph, in document order (including
paragraphs inside tables):

```json
{
  "index": 1,
  "location": "body",
  "style": "",
  "page_break": false,
  "section_break": false,
  "insertions": 0,
  "deletions": 0,
  "text": "..."
}
```

`location` is `"body"` for a top-level paragraph or `"table-N"` (1-based) for
a paragraph inside the Nth table. `text` is revision-aware: inserted text is
wrapped `[INS:...]`, deleted text `[DEL:...]`, tabs render as `\t`, and line
and page breaks render as `[BR]`.

## `validate --json`

A JSON array of check results, in the order the checks were run:

```json
{ "name": "tracking-enabled", "passed": true, "detail": "w:trackRevisions present" }
```

The command's exit status is 0 only if every check's `passed` is `true`.
Which checks run depends on the flags passed (see README); `zip-integrity`,
`tracking-enabled`, `has-changes`, `no-formatting-insertions`, and
`comments-consistent` always run. `run-properties-preserved` runs whenever
`--original` is given, alongside `paragraph-count` and `protect-numbers`.

## Exit codes

Every command follows the same convention: `0` on success, `1` on any
handled failure (ambiguous/missing match, failed validation check, bad
`--pairs` entry). An unhandled exception is a bug, not an expected failure
mode.
