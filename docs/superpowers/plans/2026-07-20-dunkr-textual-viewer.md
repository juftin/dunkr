# Dunkr Textual Viewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `dunk` MRE with `dunkr`, a read-only native Textual application that selects changed files in a sidebar and displays a scrollable rich side-by-side diff.

**Architecture:** Resolve piped or implicit Git input at the CLI boundary, parse it once into application-owned file models, and give those models to a Textual app composed of a file sidebar and diff view. The diff view returns native Rich renderables directly so no UI path serializes or reparses ANSI control sequences.

**Tech Stack:** Python 3.11+, uv, unidiff, Rich, Textual, pytest

## Global Constraints

- The Python package, executable, visible title, and documentation are named `dunkr`; the old `dunk` entry point is removed.
- The viewer is read-only and never mutates the repository or Git index.
- Input comes from piped stdin when present and otherwise from `git diff` in the current working directory.
- Interaction is limited to file selection, scrolling, responsive resizing, sidebar visibility, and quitting.
- Production UI rendering must not use forced-terminal output, ANSI serialization, or `Text.from_ansi`.
- Search, hunk commands, hunk collapsing, staging, configuration, custom themes, and alternate Git modes remain out of scope.
- Run project workflows through `task` if a Taskfile is introduced; otherwise use `uv run` and the existing project configuration.

## File Structure

- `dunkr/__init__.py`: package version.
- `dunkr/cli.py`: stdin/Git input resolution, controlling-terminal handoff, and process exit behavior.
- `dunkr/models.py`: application-owned `DiffFile` models and unified-diff parsing.
- `dunkr/rendering.py`: native Rich renderables for one selected file and its special states.
- `dunkr/app.py`: Textual `FileSidebar`, `DiffView`, and `DunkrApp`.
- `dunkr/underline_bar.py`: renamed existing reusable Rich bar renderable.
- `tests/test_cli.py`: CLI boundary behavior.
- `tests/test_models.py`: parsed metadata behavior.
- `tests/test_rendering.py`: native Rich output and style behavior.
- `tests/test_app.py`: Textual interaction and resize behavior.
- `pyproject.toml`: package and entry-point rename.
- `README.md`: `dunkr` installation, invocation, and controls.
- Remove `dunk/` and `tests/test_dunk.py` after their covered behavior has moved to the new modules.

---

### Task 1: Rename the Package and Build the CLI Input Boundary

**Files:**
- Create: `dunkr/__init__.py`
- Create: `dunkr/cli.py`
- Create: `tests/test_cli.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `InputError(message: str)`, `read_diff(stdin: TextIO, cwd: Path) -> str`, `terminal_input(stdin: TextIO) -> Iterator[None]`, and `main() -> int`.
- Consumes: `DunkrApp(diff: str, project_root: Path)` from Task 4; use a local import inside `main` so Task 1 tests can patch it before Task 4 exists.

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_cli.py` with tests that establish the exact boundary:

```python
"""Tests for dunkr's command-line boundary."""

import io
import subprocess
from pathlib import Path

import pytest

from dunkr.cli import InputError, read_diff


def test_read_diff_uses_piped_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use explicit input without invoking Git."""
    stdin = io.StringIO("diff --git a/a.py b/a.py\n")
    monkeypatch.setattr(stdin, "isatty", lambda: False)

    def unexpected_run(*args: object, **kwargs: object) -> None:
        """Fail if piped input incorrectly invokes Git."""
        raise AssertionError("git must not run for piped input")

    monkeypatch.setattr(subprocess, "run", unexpected_run)
    assert read_diff(stdin=stdin, cwd=Path("/repo")) == stdin.getvalue()


def test_read_diff_runs_git_for_a_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Obtain the working-tree diff when no pipe is present."""
    stdin = io.StringIO()
    monkeypatch.setattr(stdin, "isatty", lambda: True)
    completed = subprocess.CompletedProcess(
        args=["git", "diff", "--no-color"], returncode=0, stdout="the diff", stderr=""
    )
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: completed)

    assert read_diff(stdin=stdin, cwd=Path("/repo")) == "the diff"


def test_read_diff_reports_git_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Convert a failed implicit Git invocation into a CLI error."""
    stdin = io.StringIO()
    monkeypatch.setattr(stdin, "isatty", lambda: True)
    completed = subprocess.CompletedProcess(
        args=["git", "diff", "--no-color"], returncode=128, stdout="", stderr="not a repo"
    )
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: completed)

    with pytest.raises(InputError, match="not a repo"):
        read_diff(stdin=stdin, cwd=Path("/repo"))
```

- [ ] **Step 2: Run the CLI tests and verify the import failure**

Run: `UV_CACHE_DIR=/tmp/dunkr-uv-cache uv run pytest -q tests/test_cli.py`

Expected: FAIL because `dunkr.cli` does not exist.

- [ ] **Step 3: Implement the minimal input boundary**

Create `dunkr/__init__.py`:

```python
"""Interactive rich Git diff viewer."""

__version__ = "0.5.0b0"
```

Create `dunkr/cli.py` with:

```python
"""Command-line input and terminal handling for dunkr."""

import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, TextIO


class InputError(RuntimeError):
    """Report input that cannot be obtained or parsed."""


def read_diff(stdin: TextIO, cwd: Path) -> str:
    """Read a piped diff or obtain the working-tree diff from Git."""
    if not stdin.isatty():
        return stdin.read()
    completed = subprocess.run(
        ["git", "diff", "--no-color"],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        raise InputError(completed.stderr.strip() or "git diff failed")
    return completed.stdout


@contextmanager
def terminal_input(stdin: TextIO) -> Iterator[None]:
    """Reconnect file descriptor zero to the controlling terminal for Textual."""
    if stdin.isatty():
        yield
        return
    terminal_path = "CONIN$" if os.name == "nt" else "/dev/tty"
    stdin_fd = sys.__stdin__.fileno()
    saved_fd = os.dup(stdin_fd)
    try:
        with open(terminal_path) as terminal:
            os.dup2(terminal.fileno(), stdin_fd)
            yield
    finally:
        os.dup2(saved_fd, stdin_fd)
        os.close(saved_fd)


def main() -> int:
    """Resolve input, launch dunkr, and return a process exit status."""
    from dunkr.app import DunkrApp

    try:
        diff = read_diff(stdin=sys.stdin, cwd=Path.cwd())
    except InputError as error:
        print(f"dunkr: {error}", file=sys.stderr)
        return 1
    with terminal_input(sys.stdin):
        DunkrApp(diff=diff, project_root=Path.cwd()).run()
    return 0
```

Update `pyproject.toml`:

```toml
[project]
name = "dunkr"

[project.scripts]
dunkr = "dunkr.cli:main"

[tool.hatch.build.targets.wheel]
packages = ["dunkr"]
```

- [ ] **Step 4: Run the focused tests**

Run: `UV_CACHE_DIR=/tmp/dunkr-uv-cache uv run pytest -q tests/test_cli.py`

Expected: `3 passed`.

- [ ] **Step 5: Regenerate the lockfile and verify metadata**

Run: `UV_CACHE_DIR=/tmp/dunkr-uv-cache uv lock`

Run: `UV_CACHE_DIR=/tmp/dunkr-uv-cache uv run python -c 'import dunkr; print(dunkr.__version__)'`

Expected: lock succeeds and prints `0.5.0b0`.

- [ ] **Step 6: Commit the CLI boundary**

```bash
git add dunkr/__init__.py dunkr/cli.py tests/test_cli.py pyproject.toml uv.lock
git commit -m "✨ Add dunkr CLI input boundary"
```

### Task 2: Parse Unified Diffs into File Models

**Files:**
- Create: `dunkr/models.py`
- Create: `tests/test_models.py`

**Interfaces:**
- Consumes: unified diff text and a repository `Path`.
- Produces: `ChangeKind`, `DiffFile`, `DiffSet`, and `parse_diff(text: str, project_root: Path) -> DiffSet`.
- `DiffFile.patch` remains private parser state for the renderer; widgets consume the named metadata properties.

- [ ] **Step 1: Write failing model tests**

Create `tests/test_models.py` covering a modified file and an empty diff:

```python
"""Tests for application-owned diff models."""

from pathlib import Path

from dunkr.models import ChangeKind, parse_diff


MODIFIED_DIFF = """\
diff --git a/example.py b/example.py
index 0000000..1111111 100644
--- a/example.py
+++ b/example.py
@@ -1 +1 @@
-print("before")
+print("after")
"""


def test_parse_diff_exposes_file_metadata(tmp_path: Path) -> None:
    """Expose stable metadata without requiring widgets to inspect unidiff."""
    (tmp_path / "example.py").write_text('print("after")\n')

    diff_set = parse_diff(text=MODIFIED_DIFF, project_root=tmp_path)

    assert len(diff_set.files) == 1
    file = diff_set.files[0]
    assert file.path == "example.py"
    assert file.kind is ChangeKind.MODIFIED
    assert file.additions == 1
    assert file.deletions == 1
    assert file.target_path == tmp_path / "example.py"


def test_parse_diff_accepts_empty_input(tmp_path: Path) -> None:
    """Represent an empty working tree without raising an error."""
    assert parse_diff(text="", project_root=tmp_path).files == ()
```

Add four named tests using minimal valid unified-diff fixtures:

```python
def test_parse_added_file(tmp_path: Path) -> None:
    """Classify a /dev/null source as an added file."""
    text = "--- /dev/null\n+++ b/new.py\n@@ -0,0 +1 @@\n+new = True\n"
    file = parse_diff(text=text, project_root=tmp_path).files[0]
    assert file.kind is ChangeKind.ADDED
    assert file.target_path == tmp_path / "new.py"
    assert not file.is_binary


def test_parse_deleted_file(tmp_path: Path) -> None:
    """Classify a /dev/null target as a deleted file."""
    text = "--- a/old.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-old = True\n"
    file = parse_diff(text=text, project_root=tmp_path).files[0]
    assert file.kind is ChangeKind.DELETED
    assert file.source_path == tmp_path / "old.py"
    assert not file.is_binary


def test_parse_renamed_file(tmp_path: Path) -> None:
    """Expose both paths for a pure rename."""
    text = "diff --git a/old.py b/new.py\nsimilarity index 100%\nrename from old.py\nrename to new.py\n"
    file = parse_diff(text=text, project_root=tmp_path).files[0]
    assert file.kind is ChangeKind.RENAMED
    assert file.source_path == tmp_path / "old.py"
    assert file.target_path == tmp_path / "new.py"


def test_parse_binary_file(tmp_path: Path) -> None:
    """Classify Git's binary marker without reading file content."""
    text = "diff --git a/image.png b/image.png\nBinary files a/image.png and b/image.png differ\n"
    file = parse_diff(text=text, project_root=tmp_path).files[0]
    assert file.kind is ChangeKind.BINARY
    assert file.is_binary
```

- [ ] **Step 2: Run model tests and verify the import failure**

Run: `UV_CACHE_DIR=/tmp/dunkr-uv-cache uv run pytest -q tests/test_models.py`

Expected: FAIL because `dunkr.models` does not exist.

- [ ] **Step 3: Implement immutable models and parser mapping**

Create `dunkr/models.py`:

```python
"""Application-owned models for parsed unified diffs."""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from unidiff import PatchSet
from unidiff.errors import UnidiffParseError
from unidiff.patch import PatchedFile


class DiffParseError(ValueError):
    """Report malformed unified diff input."""


class ChangeKind(Enum):
    """Describe a file-level Git change."""

    MODIFIED = "modified"
    ADDED = "added"
    DELETED = "deleted"
    RENAMED = "renamed"
    BINARY = "binary"


@dataclass(frozen=True)
class DiffFile:
    """Stable file metadata plus parser state needed by native rendering."""

    path: str
    source_path: Path
    target_path: Path
    kind: ChangeKind
    additions: int
    deletions: int
    is_binary: bool
    patch: PatchedFile


@dataclass(frozen=True)
class DiffSet:
    """An ordered collection of changed files."""

    files: tuple[DiffFile, ...]


def _change_kind(patch: PatchedFile) -> ChangeKind:
    """Map unidiff flags to one stable application change kind."""
    if patch.is_binary_file:
        return ChangeKind.BINARY
    if patch.is_added_file:
        return ChangeKind.ADDED
    if patch.is_removed_file:
        return ChangeKind.DELETED
    if patch.is_rename:
        return ChangeKind.RENAMED
    return ChangeKind.MODIFIED


def parse_diff(text: str, project_root: Path) -> DiffSet:
    """Parse unified text into file models rooted at ``project_root``."""
    if not text.strip():
        return DiffSet(files=())
    try:
        patches = PatchSet(text)
    except (UnidiffParseError, ValueError) as error:
        raise DiffParseError(str(error)) from error
    files = tuple(
        DiffFile(
            path=patch.path,
            source_path=project_root / patch.source_file.removeprefix("a/"),
            target_path=project_root / patch.target_file.removeprefix("b/"),
            kind=_change_kind(patch),
            additions=patch.added,
            deletions=patch.removed,
            is_binary=patch.is_binary_file,
            patch=patch,
        )
        for patch in patches
    )
    return DiffSet(files=files)
```

- [ ] **Step 4: Run model tests**

Run: `UV_CACHE_DIR=/tmp/dunkr-uv-cache uv run pytest -q tests/test_models.py`

Expected: all model cases pass.

- [ ] **Step 5: Commit the model boundary**

```bash
git add dunkr/models.py tests/test_models.py
git commit -m "✨ Model parsed diff files"
```

### Task 3: Build a Native Rich File Renderer

**Files:**
- Create: `dunkr/rendering.py`
- Move: `dunk/underline_bar.py` to `dunkr/underline_bar.py`
- Create: `tests/test_rendering.py`

**Interfaces:**
- Consumes: `DiffFile` from Task 2 and the available render width supplied by Rich.
- Produces: `FileDiffRenderable(file: DiffFile)`, a native Rich renderable accepted directly by Textual.

- [ ] **Step 1: Write failing renderer tests**

Create `tests/test_rendering.py` with a non-terminal recording console:

```python
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


def test_file_diff_reflows_to_the_available_width(tmp_path: Path) -> None:
    """Fit every output line within the Rich console width."""
    (tmp_path / "example.py").write_text('print("after")\n')
    file = parse_diff(text=MODIFIED_DIFF, project_root=tmp_path).files[0]

    rendered = render_plain(FileDiffRenderable(file=file), width=60)

    assert max(map(len, rendered.splitlines())) <= 60
```

Add direct tests for deleted, binary, pure-rename, and unreadable-target states. Inspect `console.render(FileDiffRenderable(...))` and assert at least one changed-line `Segment.style.bgcolor` is present so the tests verify rich styling, not only text.

- [ ] **Step 2: Run renderer tests and verify the import failure**

Run: `UV_CACHE_DIR=/tmp/dunkr-uv-cache uv run pytest -q tests/test_rendering.py`

Expected: FAIL because `dunkr.rendering` does not exist.

- [ ] **Step 3: Implement native rendering without ANSI conversion**

Create `dunkr/rendering.py` with the complete native-rendering path below:

```python
"""Native Rich rendering for one selected diff file."""

from dataclasses import dataclass
from difflib import SequenceMatcher
from itertools import zip_longest
from typing import Iterable

from rich.console import Console, ConsoleOptions, RenderResult
from rich.rule import Rule
from rich.style import Style
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from unidiff.patch import Hunk, Line

from dunkr.models import ChangeKind, DiffFile


@dataclass(frozen=True)
class FileDiffRenderable:
    """Render one file as a width-aware side-by-side Rich diff."""

    file: DiffFile

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        """Yield native Rich objects for the selected file."""
        yield Rule(
            Text(
                f"{self.file.path}  +{self.file.additions} -{self.file.deletions}",
                style="bold",
            )
        )
        if self.file.kind is ChangeKind.BINARY:
            yield Text("Binary file", style="bold blue")
            return
        if self.file.kind is ChangeKind.DELETED:
            yield Text("File was deleted", style="bold red")
        if self.file.kind is ChangeKind.RENAMED and len(self.file.patch) == 0:
            yield Text(
                f"Renamed: {self.file.source_path.name} → {self.file.target_path.name}",
                style="cyan",
            )
            return
        yield from _render_hunks(file=self.file, width=options.max_width)


def _flush_changed_lines(
    source: list[Line], target: list[Line]
) -> list[tuple[Line | None, Line | None]]:
    """Pair adjacent removal and addition blocks for side-by-side display."""
    return list(zip_longest(source, target))


def _paired_rows(hunk: Hunk) -> list[tuple[Line | None, Line | None]]:
    """Align context and changed lines from one hunk."""
    rows: list[tuple[Line | None, Line | None]] = []
    removed: list[Line] = []
    added: list[Line] = []
    for line in hunk:
        if line.is_removed:
            removed.append(line)
        elif line.is_added:
            added.append(line)
        else:
            rows.extend(_flush_changed_lines(removed, added))
            removed.clear()
            added.clear()
            rows.append((line, line))
    rows.extend(_flush_changed_lines(removed, added))
    return rows


def _changed_ranges(left: str, right: str) -> tuple[tuple[int, int], tuple[int, int]]:
    """Return the bounds of non-equal intraline regions on both sides."""
    left_ranges: list[tuple[int, int]] = []
    right_ranges: list[tuple[int, int]] = []
    for tag, left_start, left_end, right_start, right_end in SequenceMatcher(
        a=left, b=right
    ).get_opcodes():
        if tag != "equal":
            left_ranges.append((left_start, left_end))
            right_ranges.append((right_start, right_end))
    return tuple(left_ranges), tuple(right_ranges)


def _code_cell(
    *,
    line: Line | None,
    path: str,
    background: str | None,
    ranges: tuple[tuple[int, int], ...],
) -> Text:
    """Build one numbered syntax-highlighted cell."""
    if line is None:
        return Text()
    number = line.source_line_no if line.is_removed else line.target_line_no
    value = line.value.rstrip("\n")
    try:
        lexer = Syntax.guess_lexer(path)
    except Exception:
        lexer = "text"
    code = Syntax(value, lexer=lexer, word_wrap=True).highlight(value)
    if background is not None:
        code.stylize(Style(bgcolor=background))
    for start, end in ranges:
        code.stylize(Style(bold=True, bgcolor="#6b3340"), start=start, end=end)
    return Text.assemble((f"{number or '':>4} ", "dim"), code)


def _render_hunks(file: DiffFile, width: int) -> Iterable[object]:
    """Yield width-aware side-by-side tables for every hunk."""
    for hunk in file.patch:
        yield Text(
            f"@@ -{hunk.source_start},{hunk.source_length} "
            f"+{hunk.target_start},{hunk.target_length} @@ {hunk.section_header}",
            style="dim",
        )
        table = Table.grid(expand=True, padding=(0, 1))
        table.add_column(width=max(1, width // 2))
        table.add_column(width=max(1, width - width // 2))
        for source, target in _paired_rows(hunk):
            source_value = source.value.rstrip("\n") if source is not None else ""
            target_value = target.value.rstrip("\n") if target is not None else ""
            source_ranges, target_ranges = _changed_ranges(source_value, target_value)
            table.add_row(
                _code_cell(
                    line=source,
                    path=file.path,
                    background="#3b1f24" if source is not None and source.is_removed else None,
                    ranges=source_ranges,
                ),
                _code_cell(
                    line=target,
                    path=file.path,
                    background="#183c2b" if target is not None and target.is_added else None,
                    ranges=target_ranges,
                ),
            )
        yield table
```

Keep all intermediate values as Rich objects. The module must contain no `io.StringIO`, `force_terminal=True`, `Text.from_ansi`, or `Console.print` call.

Move `dunk/underline_bar.py` to `dunkr/underline_bar.py` and update its imports only if the renderer retains the summary bar.

- [ ] **Step 4: Prove the native renderer passes its tests and has no ANSI bridge**

Run: `UV_CACHE_DIR=/tmp/dunkr-uv-cache uv run pytest -q tests/test_rendering.py`

Expected: all rendering and special-state tests pass.

Run: `rg -n "StringIO|force_terminal|from_ansi" dunkr`

Expected: no matches.

- [ ] **Step 5: Commit the renderer**

```bash
git add dunkr/rendering.py dunkr/underline_bar.py tests/test_rendering.py
git commit -m "✨ Render native Rich file diffs"
```

### Task 4: Compose the Textual App and Complete the Rename

**Files:**
- Create: `dunkr/app.py`
- Create: `tests/test_app.py`
- Modify: `dunkr/cli.py`
- Modify: `README.md`
- Delete: `dunk/`
- Delete: `tests/test_dunk.py`

**Interfaces:**
- Consumes: `parse_diff`, `DiffSet`, `DiffFile`, and `FileDiffRenderable` from Tasks 2 and 3.
- Produces: `FileSidebar`, `DiffView`, and `DunkrApp(diff: str, project_root: Path)`.

- [ ] **Step 1: Write failing Textual interaction tests**

Create `tests/test_app.py`:

```python
"""Tests for the interactive dunkr application."""

import asyncio
from pathlib import Path

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


def test_sidebar_selects_the_displayed_file(tmp_path: Path) -> None:
    """Update the diff pane when the user selects another file."""
    (tmp_path / "one.py").write_text("one = 2\n")
    (tmp_path / "two.py").write_text("two = 2\n")

    async def run_app() -> str:
        """Select the second file and return the displayed text."""
        app = DunkrApp(diff=TWO_FILE_DIFF, project_root=tmp_path)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            sidebar = app.query_one(FileSidebar)
            sidebar.index = 1
            await pilot.pause()
            return app.query_one(DiffView).render().plain

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
            return app.screen.render().plain

    assert "No changes" in asyncio.run(run_app())
```

Add the following interaction tests:

```python
def test_sidebar_binding_toggles_visibility(tmp_path: Path) -> None:
    """Hide and restore the file list with the b binding."""
    (tmp_path / "one.py").write_text("one = 2\n")
    (tmp_path / "two.py").write_text("two = 2\n")

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


def test_selected_diff_survives_resize(tmp_path: Path) -> None:
    """Keep the selected file visible after terminal reflow."""
    (tmp_path / "one.py").write_text("one = 2\n")
    (tmp_path / "two.py").write_text("two = 2\n")

    async def run_app() -> str:
        """Resize the terminal and return visible screen text."""
        app = DunkrApp(diff=TWO_FILE_DIFF, project_root=tmp_path)
        async with app.run_test(size=(120, 40)) as pilot:
            app.query_one(FileSidebar).index = 1
            await pilot.resize_terminal(width=70, height=30)
            await pilot.pause()
            return app.screen.render().plain

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
```

- [ ] **Step 2: Run app tests and verify the import failure**

Run: `UV_CACHE_DIR=/tmp/dunkr-uv-cache uv run pytest -q tests/test_app.py`

Expected: FAIL because `dunkr.app` does not exist.

- [ ] **Step 3: Implement the native Textual shell**

Create `dunkr/app.py` with these concrete components:

```python
"""Native Textual application for browsing rich file diffs."""

from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Footer, Header, ListItem, ListView, Static

from dunkr.models import DiffFile, DiffSet, parse_diff
from dunkr.rendering import FileDiffRenderable


class FileSidebar(ListView):
    """Select a changed file from the parsed diff."""

    def __init__(self, files: tuple[DiffFile, ...]) -> None:
        """Build file rows with compact change counts."""
        self.files = files
        super().__init__(
            *(
                ListItem(
                    Static(
                        Text.assemble(
                            file.path,
                            "  ",
                            (f"+{file.additions}", "green"),
                            " ",
                            (f"-{file.deletions}", "red"),
                        )
                    ),
                    id=f"file-{index}",
                )
                for index, file in enumerate(files)
            ),
            id="files",
        )


class DiffView(Static):
    """Display one selected file as a native Rich renderable."""

    def show_file(self, file: DiffFile) -> None:
        """Replace the pane content with ``file``."""
        self.update(FileDiffRenderable(file=file))


class DunkrApp(App[None]):
    """Browse a parsed Git diff by changed file."""

    BINDINGS = [("q", "quit", "Quit"), ("b", "toggle_sidebar", "Files")]
    CSS = """
    Screen { background: #0d0f0b; }
    #body { height: 1fr; }
    #files { width: 32; min-width: 20; border-right: solid #3e4036; }
    #diff-scroll { width: 1fr; }
    #diff { width: 1fr; }
    #empty { width: 1fr; height: 1fr; content-align: center middle; }
    .sidebar-hidden #files { display: none; }
    """

    def __init__(self, diff: str, project_root: Path) -> None:
        """Parse ``diff`` once and initialize selected-file state."""
        super().__init__()
        self.diff_set: DiffSet = parse_diff(text=diff, project_root=project_root)

    def compose(self) -> ComposeResult:
        """Compose app chrome, file selection, and scrollable diff content."""
        yield Header(show_clock=False)
        if not self.diff_set.files:
            yield Static("No changes", id="empty")
        else:
            with Horizontal(id="body"):
                yield FileSidebar(files=self.diff_set.files)
                with VerticalScroll(id="diff-scroll"):
                    yield DiffView(id="diff")
        yield Footer()

    def on_mount(self) -> None:
        """Select and display the first changed file."""
        self.title = "dunkr"
        if self.diff_set.files:
            sidebar = self.query_one(FileSidebar)
            sidebar.index = 0
            self.query_one(DiffView).show_file(self.diff_set.files[0])

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Display the file corresponding to the highlighted sidebar row."""
        if event.list_view.id == "files" and event.list_view.index is not None:
            self.query_one(DiffView).show_file(
                self.diff_set.files[event.list_view.index]
            )

    def action_toggle_sidebar(self) -> None:
        """Toggle the file sidebar without changing selection."""
        self.query_one("#body").toggle_class("sidebar-hidden")
```

- [ ] **Step 4: Run app tests and the complete test suite**

Run: `UV_CACHE_DIR=/tmp/dunkr-uv-cache uv run pytest -q tests/test_app.py`

Expected: all app interaction tests pass.

Run: `UV_CACHE_DIR=/tmp/dunkr-uv-cache uv run pytest -q`

Expected: all tests pass.

- [ ] **Step 5: Complete documentation and remove the old package**

Rewrite README usage and controls around:

```markdown
# dunkr

A rich, interactive side-by-side Git diff viewer built with Textual.

```console
git diff | dunkr
dunkr
```

Use the file sidebar or mouse to select a change, scroll the diff normally,
press `b` to toggle the sidebar, and press `q` to quit. `dunkr` is read-only.
```

Delete `dunk/` and `tests/test_dunk.py` only after all equivalent tests exist in the new suite. Search for stale names:

Run: `rg -n "\bdunk\b|DunkApp" README.md pyproject.toml dunkr tests`

Expected: no old package, command, or class references; incidental prose about Git diffs is allowed.

- [ ] **Step 6: Run formatting, linting, tests, and build verification**

Because this repository has no Taskfile, run:

```bash
ruff format dunkr tests
ruff format --check dunkr tests
ruff check dunkr tests
UV_CACHE_DIR=/tmp/dunkr-uv-cache uv run pytest -q
UV_CACHE_DIR=/tmp/dunkr-uv-cache uv build
git diff --check
```

Expected: every command exits zero, all tests pass, and wheel/sdist artifacts build successfully.

- [ ] **Step 7: Perform a real terminal smoke test**

From a normal interactive terminal in a Git repository with changes, run:

```bash
UV_CACHE_DIR=/tmp/dunkr-uv-cache uv run dunkr
git diff HEAD | UV_CACHE_DIR=/tmp/dunkr-uv-cache uv run dunkr
```

For each invocation verify: the sidebar appears, selecting a file updates the diff, scrolling works, `b` toggles the sidebar, `q` exits cleanly, and no control sequences remain in the shell.

- [ ] **Step 8: Commit the completed app**

```bash
git add README.md pyproject.toml uv.lock dunkr tests
git add -u dunk tests/test_dunk.py
git commit -m "✨ Build the interactive dunkr viewer"
```
