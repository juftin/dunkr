"""Tests for native Rich diff rendering."""

from pathlib import Path

import pytest
from rich.console import Console
from rich.syntax import Syntax

from dunkr.models import parse_diff
from dunkr.rendering import FileDiffRenderable, _paired_rows
from tests.test_models import MODIFIED_DIFF


def render_plain(renderable: object, width: int = 100) -> str:
    """Render without ANSI serialization and return recorded plain text."""
    console = Console(width=width, record=True, force_terminal=False)
    console.print(renderable)
    return console.export_text()


def test_file_diff_renders_source_and_target_lines(tmp_path: Path) -> None:
    """Show both sides of a modified line in the selected file."""
    (tmp_path / "example.py").write_text('print("after")\n')
    file = parse_diff(text=MODIFIED_DIFF, project_root=tmp_path).files[0]

    rendered = render_plain(FileDiffRenderable(file=file))

    assert 'print("before")' in rendered
    assert 'print("after")' in rendered
    assert "example.py" in rendered


def test_file_diff_preserves_source_and_target_context_numbers(
    tmp_path: Path,
) -> None:
    """Number context independently when source and target offsets differ."""
    text = """\
--- a/example.py
+++ b/example.py
@@ -10,2 +20,2 @@
 context
-before
+after
"""
    (tmp_path / "example.py").write_text("context\nafter\n")
    file = parse_diff(text=text, project_root=tmp_path).files[0]

    rendered = render_plain(FileDiffRenderable(file=file))

    assert "  10 context" in rendered
    assert "  20 context" in rendered


def test_file_diff_applies_changed_line_backgrounds(tmp_path: Path) -> None:
    """Keep change highlighting as native Rich segment styles."""
    (tmp_path / "example.py").write_text('print("after")\n')
    file = parse_diff(text=MODIFIED_DIFF, project_root=tmp_path).files[0]
    console = Console(width=100, force_terminal=False)

    segments = list(console.render(FileDiffRenderable(file=file)))

    assert any(
        segment.style is not None and segment.style.bgcolor is not None
        for segment in segments
        if "print" in segment.text
    )


def test_file_diff_guesses_lexer_once_per_render(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Reuse one lexer decision for all cells in a selected file render."""
    (tmp_path / "example.py").write_text('print("after")\n')
    file = parse_diff(text=MODIFIED_DIFF, project_root=tmp_path).files[0]
    guessed_paths: list[str] = []

    def guess_lexer(path: str) -> str:
        """Record lexer guesses while returning a stable test lexer."""
        guessed_paths.append(path)
        return "python"

    monkeypatch.setattr(Syntax, "guess_lexer", staticmethod(guess_lexer))

    render_plain(FileDiffRenderable(file=file))

    assert guessed_paths == ["example.py"]


def test_file_diff_reflows_to_the_available_width(tmp_path: Path) -> None:
    """Fit every output line within the Rich console width."""
    (tmp_path / "example.py").write_text('print("after")\n')
    file = parse_diff(text=MODIFIED_DIFF, project_root=tmp_path).files[0]

    rendered = render_plain(FileDiffRenderable(file=file), width=60)

    assert max(map(len, rendered.splitlines())) <= 60


def test_file_diff_describes_a_deleted_file(tmp_path: Path) -> None:
    """Describe a deleted file without trying to read its absent target."""
    text = "--- a/old.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-old = True\n"
    file = parse_diff(text=text, project_root=tmp_path).files[0]

    rendered = render_plain(FileDiffRenderable(file=file))

    assert "File was deleted" in rendered
    assert "old = True" in rendered


def test_file_diff_describes_a_binary_file(tmp_path: Path) -> None:
    """Describe binary content instead of attempting text rendering."""
    text = (
        "diff --git a/image.png b/image.png\n"
        "Binary files a/image.png and b/image.png differ\n"
    )
    file = parse_diff(text=text, project_root=tmp_path).files[0]

    rendered = render_plain(FileDiffRenderable(file=file))

    assert "Binary file" in rendered


def test_file_diff_describes_a_pure_rename(tmp_path: Path) -> None:
    """Show both paths when a rename has no content changes."""
    text = (
        "diff --git a/pkg/old/name.py b/pkg/new/name.py\n"
        "similarity index 100%\n"
        "rename from pkg/old/name.py\n"
        "rename to pkg/new/name.py\n"
    )
    file = parse_diff(text=text, project_root=tmp_path).files[0]

    rendered = render_plain(FileDiffRenderable(file=file))

    assert "Renamed: pkg/old/name.py → pkg/new/name.py" in rendered


def test_file_diff_describes_nested_rename_with_content_changes(
    tmp_path: Path,
) -> None:
    """Show full old and new repository paths before rendering rename hunks."""
    text = (
        "diff --git a/pkg/old/name.py b/pkg/new/name.py\n"
        "similarity index 80%\n"
        "rename from pkg/old/name.py\n"
        "rename to pkg/new/name.py\n"
        "--- a/pkg/old/name.py\n"
        "+++ b/pkg/new/name.py\n"
        "@@ -1 +1 @@\n"
        "-old = True\n"
        "+new = True\n"
    )
    file = parse_diff(text=text, project_root=tmp_path).files[0]

    rendered = render_plain(FileDiffRenderable(file=file))

    assert "Renamed: pkg/old/name.py → pkg/new/name.py" in rendered
    assert "old = True" in rendered
    assert "new = True" in rendered


def test_file_diff_renders_without_reading_target(tmp_path: Path) -> None:
    """Render exclusively from patch content when the target does not exist."""
    file = parse_diff(text=MODIFIED_DIFF, project_root=tmp_path).files[0]

    rendered = render_plain(FileDiffRenderable(file=file))

    assert 'print("before")' in rendered
    assert 'print("after")' in rendered
    assert "Unable to read target file" not in rendered


def test_no_newline_records_remain_metadata_while_changes_pair(
    tmp_path: Path,
) -> None:
    """Ignore no-newline markers without splitting removal/addition pairs."""
    text = (
        "--- a/example.py\n"
        "+++ b/example.py\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "\\ No newline at end of file\n"
        "+new\n"
        "\\ No newline at end of file\n"
    )
    file = parse_diff(text=text, project_root=tmp_path).files[0]

    rows = _paired_rows(file.patch[0])

    assert len(rows) == 1
    source, target = rows[0]
    assert source is not None and source.value == "old\n"
    assert target is not None and target.value == "new\n"
