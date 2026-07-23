# Dunkr Visual Regression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn dunkr into an all-files diff browser and add a deterministic, locally runnable Textual SVG visual-regression suite.

**Architecture:** A fixture builder creates a temporary Git repository with one mixed change set. `DunkrApp` renders all parsed files in one Rich document and maps sidebar rows to the document's file-section offsets. A test harness drives the same app states at a fixed size and compares normalized Textual SVG output to committed baselines.

**Tech Stack:** Python 3.11+, pytest, Textual, Rich, unidiff, uv

## Global Constraints

- Work directly on `master`; do not create or use a worktree.
- Do not modify staged `file.md`.
- The fixture includes modified, added, deleted, renamed, renamed-with-content, binary, and no-final-newline changes.
- The app displays every changed file in one scrollable document; sidebar selection scrolls to sections and never replaces document content.
- Baselines are normalized Textual SVG at 140×42; they are committed under `tests/snapshots/`.
- Only `dunkr-snapshots --update` writes baselines; PNG previews are ignored under `artifacts/screenshots/`.
- Do not add search, staging, filtering, a selected-file mode, custom themes, pixel-comparison dependencies, or configuration.

---

### Task 1: Build the Deterministic Demo Fixture and Native All-Files Renderable

**Files:**
- Create: `dunkr/demo.py`
- Create: `tests/test_demo.py`
- Modify: `dunkr/rendering.py`
- Modify: `dunkr/app.py`
- Modify: `tests/test_app.py`

**Interfaces:**
- Produces: `DemoRepository(root: Path, diff: str)`, `create_demo_repository() -> Iterator[DemoRepository]`, `AllFilesRenderable(files: tuple[DiffFile, ...])`, and `DunkrApp.section_offsets: dict[str, int]`.
- Consumes: existing `DiffFile`, `DiffSet`, and `FileDiffRenderable`.

- [ ] **Step 1: Write failing fixture and all-files behavior tests**

```python
def test_demo_repository_contains_every_change_kind() -> None:
    """Build a self-contained mixed diff for demos and visual tests."""
    with create_demo_repository() as demo:
        files = parse_diff(text=demo.diff, project_root=demo.root).files
    assert [file.kind for file in files] == [
        ChangeKind.MODIFIED,
        ChangeKind.ADDED,
        ChangeKind.DELETED,
        ChangeKind.RENAMED,
        ChangeKind.RENAMED,
        ChangeKind.BINARY,
        ChangeKind.MODIFIED,
    ]


def test_sidebar_selection_scrolls_to_an_existing_section() -> None:
    """Keep one document and navigate its file anchors from the sidebar."""
    with create_demo_repository() as demo:
        app = DunkrApp(diff=demo.diff, project_root=demo.root)
        async with app.run_test(size=(140, 42)) as pilot:
            await pilot.pause()
            before = _widget_text(app.query_one(DiffView))
            app.query_one(FileSidebar).index = 4
            await pilot.pause()
            after = _widget_text(app.query_one(DiffView))
            assert after == before
            assert app.query_one("#diff-scroll", VerticalScroll).scroll_offset.y > 0
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `UV_CACHE_DIR=/tmp/dunkr-uv-cache uv run pytest -q tests/test_demo.py tests/test_app.py`

Expected: FAIL because the fixture module and all-files document do not exist.

- [ ] **Step 3: Implement fixture and document rendering**

Implement `create_demo_repository()` with `TemporaryDirectory`, `git init`, a committed base tree, and only `subprocess.run([...], check=True, cwd=root)` calls. Populate the named paths in the design spec, then return the output of `git diff --no-color --find-renames`.

Add this renderable in `dunkr/rendering.py`:

```python
@dataclass(frozen=True)
class AllFilesRenderable:
    """Render every parsed file in one ordered Rich document."""

    files: tuple[DiffFile, ...]

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        """Yield each file's existing native renderer in diff order."""
        for file in self.files:
            yield FileDiffRenderable(file=file)
```

Update `DiffView.show_files(files)` to call `self.update(AllFilesRenderable(files=files))`. On mount call `show_files(self.diff_set.files)` once. In `on_list_view_highlighted`, keep the same renderable and scroll to the stored section offset with `scroll_to(y=offset, animate=False, immediate=True)`.

Derive offsets after layout by rendering each `FileDiffRenderable` through the app's Rich console at the diff view width and accumulating the number of rendered lines. Store paths as keys in `section_offsets` and recompute on resize before restoring the current sidebar selection's offset.

- [ ] **Step 4: Run focused tests and the full suite**

Run: `UV_CACHE_DIR=/tmp/dunkr-uv-cache uv run pytest -q tests/test_demo.py tests/test_app.py`

Run: `UV_CACHE_DIR=/tmp/dunkr-uv-cache uv run pytest -q`

Expected: all tests pass.

- [ ] **Step 5: Commit the all-files behavior**

```bash
git add dunkr/demo.py dunkr/rendering.py dunkr/app.py tests/test_demo.py tests/test_app.py
git commit -m "✨ Render all diff files in one view"
```

### Task 2: Add SVG Baselines, Preview Output, and Local Commands

**Files:**
- Create: `tests/visual.py`
- Create: `tests/test_visual_regression.py`
- Create: `tests/snapshots/all-files-overview.svg`
- Create: `tests/snapshots/rename-section.svg`
- Create: `tests/snapshots/binary-section.svg`
- Create: `tests/snapshots/sidebar-hidden.svg`
- Create: `dunkr/snapshots.py`
- Modify: `pyproject.toml`
- Modify: `.gitignore`
- Modify: `README.md`

**Interfaces:**
- Produces: `capture_snapshot(name: str, app: DunkrApp) -> str`, `normalize_svg(svg: str) -> str`, `assert_snapshot(name: str, svg: str) -> None`, and `main(argv: Sequence[str] | None = None) -> int` in `dunkr.snapshots`.
- Consumes: `create_demo_repository()` and `DunkrApp` from Task 1.

- [ ] **Step 1: Write failing visual-regression tests**

```python
@pytest.mark.parametrize(
    "name,action",
    [
        ("all-files-overview", lambda pilot, app: None),
        ("rename-section", lambda pilot, app: set_sidebar_index(app, 3)),
        ("binary-section", lambda pilot, app: set_sidebar_index(app, 5)),
        ("sidebar-hidden", lambda pilot, app: pilot.press("b")),
    ],
)
def test_visual_baseline(name: str, action: SnapshotAction) -> None:
    """Compare deterministic Textual SVG output with its committed baseline."""
    svg = asyncio.run(capture_demo_state(action=action, size=(140, 42)))
    assert_snapshot(name=name, svg=svg)


def test_snapshot_command_requires_update_to_write_baselines(tmp_path: Path) -> None:
    """Prevent ordinary test runs from rewriting visual expectations."""
    assert main(argv=["--output", str(tmp_path)]) == 1
    assert main(argv=["--output", str(tmp_path), "--update"]) == 0
```

- [ ] **Step 2: Run visual tests and verify the missing-baseline failure**

Run: `UV_CACHE_DIR=/tmp/dunkr-uv-cache uv run pytest -q tests/test_visual_regression.py`

Expected: FAIL because snapshot helpers and committed SVG files are absent.

- [ ] **Step 3: Implement SVG capture and command entry points**

Implement `normalize_svg` by removing only the `<title>` value and generated timestamp attributes with compiled regular expressions. `capture_demo_state` must use `DunkrApp.run_test(size=(140, 42))`, wait for `pilot.pause()`, run the requested navigation action, wait again, then call `app.export_screenshot(title=name, simplify=True)`.

Implement `dunkr.snapshots.main` with `argparse` flags:

```python
parser.add_argument("--update", action="store_true")
parser.add_argument("--preview", action="store_true")
parser.add_argument("--output", type=Path, default=Path("tests/snapshots"))
```

Without `--update`, return status 1 when a baseline is missing or differs. With `--update`, write normalized SVGs. With `--preview`, use `cairosvg.svg2png(bytestring=svg.encode(), write_to=preview_path)` to render each capture to `artifacts/screenshots/<name>.png`; never add those files to Git. Add `cairosvg` as a preview-only development dependency with `uv add --dev cairosvg`.

Add scripts to `pyproject.toml`:

```toml
[project.scripts]
dunkr-demo = "dunkr.demo:main"
dunkr-snapshots = "dunkr.snapshots:main"
```

Add `artifacts/screenshots/` to `.gitignore`. Document all three commands in README.

- [ ] **Step 4: Generate and commit baselines intentionally**

Run: `UV_CACHE_DIR=/tmp/dunkr-uv-cache uv run dunkr-snapshots --update`

Run: `UV_CACHE_DIR=/tmp/dunkr-uv-cache uv run dunkr-snapshots`

Expected: update writes four named SVGs; comparison exits zero.

- [ ] **Step 5: Verify and commit the visual suite**

Run:

```bash
UV_CACHE_DIR=/tmp/dunkr-uv-cache uv run pytest -q
UV_CACHE_DIR=/tmp/dunkr-uv-cache uv run ruff check .
UV_CACHE_DIR=/tmp/dunkr-uv-cache uv run ruff format --check .
UV_CACHE_DIR=/tmp/dunkr-uv-cache uv build
git diff --check
```

Expected: every command exits zero.

```bash
git add tests/visual.py tests/test_visual_regression.py tests/snapshots dunkr/snapshots.py pyproject.toml .gitignore README.md
git commit -m "✅ Add dunkr visual regression baselines"
```
