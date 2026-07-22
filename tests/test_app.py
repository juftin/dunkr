"""Tests for the interactive dunkr application."""

import asyncio
from pathlib import Path

from textual.containers import VerticalScroll
from textual.geometry import Region
from textual.widget import Widget

from dunkr.app import DiffView, DunkrApp, FileSidebar


TWO_FILE_DIFF = """\
diff --git a/one.py b/one.py
--- a/one.py
+++ b/one.py
@@ -1 +1 @@
-one = 1
+one = 2
diff --git a/two.py b/two.py
--- a/two.py
+++ b/two.py
@@ -1 +1 @@
-two = 1
+two = 2
"""
"""A minimal two-file diff used by interaction tests."""


def _write_changed_files(project_root: Path) -> None:
    """Create target files referenced by ``TWO_FILE_DIFF``."""
    (project_root / "one.py").write_text("one = 2\n")
    (project_root / "two.py").write_text("two = 2\n")


def _widget_text(widget: Widget) -> str:
    """Return a widget's rendered cells as plain text."""
    crop = Region(
        x=0,
        y=0,
        width=widget.size.width,
        height=widget.virtual_size.height,
    )
    return "\n".join(strip.text for strip in widget.render_lines(crop))


def test_sidebar_selects_the_displayed_file(tmp_path: Path) -> None:
    """Update the diff pane when the user selects another file."""
    _write_changed_files(project_root=tmp_path)

    async def run_app() -> str:
        """Select the second file and return the visible text."""
        app = DunkrApp(diff=TWO_FILE_DIFF, project_root=tmp_path)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.query_one(FileSidebar).index = 1
            await pilot.pause()
            return _widget_text(widget=app.query_one(DiffView))

    rendered = asyncio.run(run_app())
    assert "two.py" in rendered
    assert "two = 2" in rendered


def test_empty_diff_shows_no_changes(tmp_path: Path) -> None:
    """Show a useful empty state instead of an empty file list."""

    async def run_app() -> str:
        """Mount the empty app and return visible text."""
        app = DunkrApp(diff="", project_root=tmp_path)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            return _widget_text(widget=app.query_one("#empty"))

    assert "No changes" in asyncio.run(run_app())


def test_sidebar_binding_toggles_visibility(tmp_path: Path) -> None:
    """Hide and restore the file list with the b binding."""
    _write_changed_files(project_root=tmp_path)

    async def run_app() -> tuple[bool, bool]:
        """Return hidden state after each toggle."""
        app = DunkrApp(diff=TWO_FILE_DIFF, project_root=tmp_path)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("b")
            hidden = app.query_one("#body").has_class("sidebar-hidden")
            await pilot.press("b")
            restored = not app.query_one("#body").has_class("sidebar-hidden")
            return hidden, restored

    assert asyncio.run(run_app()) == (True, True)


def test_sidebar_binding_is_safe_for_empty_diff(tmp_path: Path) -> None:
    """Treat the sidebar binding as a no-op when there is no file list."""

    async def run_app() -> str:
        """Press b in the empty state and return its visible message."""
        app = DunkrApp(diff="", project_root=tmp_path)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.press("b")
            await pilot.pause()
            return _widget_text(widget=app.query_one("#empty"))

    assert "No changes" in asyncio.run(run_app())


def test_file_selection_scrolls_new_diff_to_home(tmp_path: Path) -> None:
    """Start each newly selected file at the top of its diff."""
    line_count = 80

    def file_patch(name: str) -> str:
        """Build one long changed-file patch that requires scrolling."""
        removed = "".join(f"-{name}_{index} = 1\n" for index in range(line_count))
        added = "".join(f"+{name}_{index} = 2\n" for index in range(line_count))
        return (
            f"diff --git a/{name}.py b/{name}.py\n"
            f"--- a/{name}.py\n"
            f"+++ b/{name}.py\n"
            f"@@ -1,{line_count} +1,{line_count} @@\n"
            f"{removed}{added}"
        )

    text = file_patch("one") + file_patch("two")
    (tmp_path / "one.py").write_text(
        "".join(f"one_{index} = 2\n" for index in range(line_count))
    )
    (tmp_path / "two.py").write_text(
        "".join(f"two_{index} = 2\n" for index in range(line_count))
    )

    async def run_app() -> tuple[int, int]:
        """Scroll the first diff, select the second, and return both offsets."""
        app = DunkrApp(diff=text, project_root=tmp_path)
        async with app.run_test(size=(120, 20)) as pilot:
            await pilot.pause()
            scroll = app.query_one("#diff-scroll", VerticalScroll)
            scroll.scroll_end(animate=False)
            await pilot.pause()
            before = scroll.scroll_offset.y
            app.query_one(FileSidebar).index = 1
            await pilot.pause()
            return before, scroll.scroll_offset.y

    before, after = asyncio.run(run_app())
    assert before > 0
    assert after == 0


def test_selected_diff_survives_resize(tmp_path: Path) -> None:
    """Keep the selected file visible after terminal reflow."""
    _write_changed_files(project_root=tmp_path)

    async def run_app() -> str:
        """Resize the terminal and return visible screen text."""
        app = DunkrApp(diff=TWO_FILE_DIFF, project_root=tmp_path)
        async with app.run_test(size=(120, 40)) as pilot:
            app.query_one(FileSidebar).index = 1
            await pilot.pause()
            await pilot.resize_terminal(width=70, height=30)
            await pilot.pause()
            return _widget_text(widget=app.query_one(DiffView))

    assert "two.py" in asyncio.run(run_app())


def test_q_binding_exits(tmp_path: Path) -> None:
    """Exit through the documented q binding."""

    async def run_app() -> bool:
        """Press q and report whether the app stopped."""
        app = DunkrApp(diff="", project_root=tmp_path)
        async with app.run_test() as pilot:
            await pilot.press("q")
            await pilot.pause()
            return app.is_running

    assert not asyncio.run(run_app())
