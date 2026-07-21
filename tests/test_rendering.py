"""Tests for native Rich diff rendering."""

from pathlib import Path

from rich.console import Console

from dunkr.models import parse_diff
from dunkr.rendering import FileDiffRenderable
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
        "diff --git a/old.py b/new.py\n"
        "similarity index 100%\n"
        "rename from old.py\n"
        "rename to new.py\n"
    )
    file = parse_diff(text=text, project_root=tmp_path).files[0]

    rendered = render_plain(FileDiffRenderable(file=file))

    assert "Renamed: old.py → new.py" in rendered


def test_file_diff_reports_an_unreadable_target(tmp_path: Path) -> None:
    """Show a local error when a modified target file cannot be read."""
    file = parse_diff(text=MODIFIED_DIFF, project_root=tmp_path).files[0]

    rendered = render_plain(FileDiffRenderable(file=file))

    assert "Unable to read target file: example.py" in rendered
