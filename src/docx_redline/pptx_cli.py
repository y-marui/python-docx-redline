"""CLI for exact-range PowerPoint review comments."""

from __future__ import annotations

import json
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import typer
from lxml import etree

from .errors import RedlineError
from .package import DocxPackage
from .pptx import object_targets, slides, text_targets
from .pptx_comments import add_comment, apply_batch, list_comments
from .pptx_validate import validate as check

app = typer.Typer(
    help="PowerPoint review comments anchored to exact text.", no_args_is_help=True
)


def _run(action: Callable[[], Any]) -> Any:
    try:
        return action()
    except (
        RedlineError,
        ValueError,
        KeyError,
        OSError,
        zipfile.BadZipFile,
        etree.XMLSyntaxError,
    ) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(1) from error


def _json(value: object) -> None:
    typer.echo(json.dumps(value, ensure_ascii=False, indent=2))


def _edit(source: Path, out: Path, operation: Callable[[DocxPackage], object]) -> None:
    def action() -> None:
        if out.exists() or out.resolve() == source.resolve():
            raise RedlineError("Output must be a new file, distinct from input")
        pkg = DocxPackage(source)
        result = operation(pkg)
        check(pkg)
        out.parent.mkdir(parents=True, exist_ok=True)
        pkg.save(out)
        try:
            check(DocxPackage(out), DocxPackage(source))
        except Exception:
            out.unlink()
            raise
        typer.echo(f"OK: {result} -> {out}")

    _run(action)


@app.command("inspect")
def inspect_cmd(
    input_path: Path = typer.Argument(..., exists=True, readable=True),
) -> None:
    """List supported ordinary slide text shapes as JSON (slide order, shape ID)."""

    def action() -> None:
        pkg = DocxPackage(input_path)
        _json(
            {
                "text": [t.info() for s in slides(pkg) for t in text_targets(s)],
                "objects": [t.info() for s in slides(pkg) for t in object_targets(s)],
            }
        )

    _run(action)


@app.command("add-comment")
def add_comment_cmd(
    input_path: Path = typer.Argument(..., exists=True, readable=True),
    text: str = typer.Option(..., "--text"),
    author: str = typer.Option(..., "--author"),
    out: Path = typer.Option(..., "--out"),
    match: str | None = typer.Option(None, "--match"),
    slide: int | None = typer.Option(None, "--slide", min=1),
    shape_id: str | None = typer.Option(None, "--shape-id"),
    object_id: str | None = typer.Option(None, "--object-id"),
    occurrence: int | None = typer.Option(None, "--occurrence", min=1),
    slide_level: bool = typer.Option(False, "--slide-level"),
) -> None:
    """Attach to --match; use --slide-level explicitly for whole-slide feedback."""
    _edit(
        input_path,
        out,
        lambda pkg: add_comment(
            pkg,
            text,
            author=author,
            match=match,
            slide=slide,
            shape_id=shape_id,
            object_id=object_id,
            occurrence=occurrence,
            slide_level=slide_level,
        ),
    )


@app.command("add-comments-batch")
def batch_cmd(
    input_path: Path = typer.Argument(..., exists=True, readable=True),
    comments: Path = typer.Option(..., "--comments", exists=True, readable=True),
    author: str = typer.Option(..., "--author"),
    out: Path = typer.Option(..., "--out"),
) -> None:
    """Add all JSON comments or write no output if any selector fails."""
    entries = _run(lambda: json.loads(comments.read_text(encoding="utf-8")))
    _edit(
        input_path,
        out,
        lambda pkg: f"{len(apply_batch(pkg, entries, author=author))} comments",
    )


@app.command("list-comments")
def list_cmd(
    input_path: Path = typer.Argument(..., exists=True, readable=True),
) -> None:
    """List classic and modern comments, including modern text offsets, as JSON."""
    _run(lambda: _json(list_comments(DocxPackage(input_path))))


@app.command("validate")
def validate_cmd(
    input_path: Path = typer.Argument(..., exists=True, readable=True),
    original: Path | None = typer.Option(
        None, "--original", exists=True, readable=True
    ),
) -> None:
    """Check modern anchors and, with --original, preservation of source content."""
    count = _run(
        lambda: check(
            DocxPackage(input_path), DocxPackage(original) if original else None
        )
    )
    typer.echo(f"OK: {count} modern comments; structural validation passed")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
