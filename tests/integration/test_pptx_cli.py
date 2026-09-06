import json

from typer.testing import CliRunner

from docx_redline.pptx_cli import app

runner = CliRunner()


def test_cli_batch_then_validate(pptx_path, tmp_path):
    entries = tmp_path / "comments.json"
    entries.write_text(
        json.dumps([{"text": "Use Autumn", "match": "Autum", "slide": 1}])
    )
    out = tmp_path / "review.pptx"
    result = runner.invoke(
        app,
        [
            "add-comments-batch",
            str(pptx_path),
            "--comments",
            str(entries),
            "--author",
            "Reviewer",
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    result = runner.invoke(app, ["validate", str(out), "--original", str(pptx_path)])
    assert result.exit_code == 0, result.output
    listed = runner.invoke(app, ["list-comments", str(out)])
    assert json.loads(listed.output)[0]["start"] == 5


def test_cli_failed_batch_writes_no_output(pptx_path, tmp_path):
    entries = tmp_path / "comments.json"
    entries.write_text(
        json.dumps(
            [{"text": "one", "match": "Autum"}, {"text": "two", "match": "absent"}]
        )
    )
    out = tmp_path / "review.pptx"
    result = runner.invoke(
        app,
        [
            "add-comments-batch",
            str(pptx_path),
            "--comments",
            str(entries),
            "--author",
            "Reviewer",
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 1
    assert not out.exists()


def test_cli_refuses_overwrite(pptx_path, tmp_path):
    out = tmp_path / "existing.pptx"
    out.write_bytes(b"preserve")
    result = runner.invoke(
        app,
        [
            "add-comment",
            str(pptx_path),
            "--match",
            "Autum",
            "--text",
            "fix",
            "--author",
            "Reviewer",
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 1
    assert out.read_bytes() == b"preserve"


def test_cli_inspect_slide_order(pptx_path):
    result = runner.invoke(app, ["inspect", str(pptx_path)])
    assert result.exit_code == 0
    report = json.loads(result.output)
    assert report["text"][0]["part"] == "ppt/slides/slide7.xml"
    assert report["objects"][0]["object_id"] == "4"
