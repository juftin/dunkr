# Dunkr All-Files Visual Regression Design

## Goal

Make `dunkr` visually testable with a deterministic mixed Git diff and
committed Textual SVG baselines. Change the application from a selected-file
diff pane to one long, scrollable all-files diff, with the sidebar acting as a
file-section index.

## Scope

This change provides:

- a deterministic fixture repository with modified, added, deleted, renamed,
  renamed-with-content, binary, and no-final-newline changes;
- one interactive local demo command that opens that entire fixture in a single
  `dunkr` UI;
- a long, ordered diff document containing every changed file;
- a sidebar that lists the same files and scrolls to their document sections;
- named Textual SVG visual-regression baselines at fixed dimensions;
- an explicit local baseline-update command; and
- disposable PNG previews for agent visual inspection, excluded from Git.

This change does not add search, staging, hunk actions, filtering, a second
selected-file mode, configurable themes, or pixel-comparison dependencies.

## Fixture Repository

The test helper creates a temporary Git repository from scratch. It commits a
base tree, changes the working tree into the required mixed state, and obtains
the fixture input with `git diff --no-color`.

The changed tree contains these exact categories:

| Path / operation | Purpose |
| --- | --- |
| Modify `src/calculator.py` | Syntax and intraline change rendering. |
| Add `docs/guide.md` | Added-file header and contents. |
| Delete `legacy/old_config.py` | Deleted-file state. |
| Rename `assets/old_name.txt` to `assets/new_name.txt` | Pure rename label. |
| Rename `src/old_module.py` to `src/new_module.py` and edit it | Rename-with-content rendering. |
| Change `assets/logo.bin` | Binary-file state. |
| Modify `notes/no_newline.txt` without a final newline | No-newline metadata handling. |

The helper returns the diff text and repository root. It never relies on the
project's own Git state.

## All-Files Application View

`DunkrApp` retains its parsed `DiffSet`, but `DiffView` receives the complete
ordered collection and renders every `FileDiffRenderable` in a single native
Rich document. File headers remain visually distinct and appear in input order.

The application calculates a stable section target for every file after the
long document is laid out. `FileSidebar` selection scrolls `#diff-scroll` to
that file header without replacing the document. The selected sidebar row
remains highlighted while the user scrolls manually.

The first file is selected on mount and the pane starts at the document top.
The existing `b` action still hides or restores the sidebar. Empty diffs retain
their centered `No changes` state and `b` remains a safe no-op.

## Screenshot Harness

`tests/visual.py` exposes a small test-only API:

- `create_demo_repository() -> DemoRepository` creates the deterministic
  fixture and returns its diff and root.
- `capture_snapshot(name, app, pilot) -> str` waits for layout stabilization,
  calls `app.export_screenshot(simplify=True)`, and returns normalized SVG.
- `assert_snapshot(name, svg)` compares it with a committed baseline under
  `tests/snapshots/`.
- `update_snapshots()` rewrites baselines only when the explicit update command
  is requested.

Every capture uses the same terminal size, 140 columns by 42 rows, and waits
for one Textual pilot pause after mounting or navigation. Snapshot comparison
uses normalized SVG text: volatile metadata is removed, but all rendered layout
and styles remain significant.

## Baselines and Local Commands

Committed SVG files live under `tests/snapshots/`:

- `all-files-overview.svg`;
- `rename-section.svg`;
- `binary-section.svg`; and
- `sidebar-hidden.svg`.

The project adds these local commands:

```console
uv run dunkr-demo
uv run dunkr-snapshots
uv run dunkr-snapshots --update
uv run dunkr-snapshots --preview
```

`dunkr-demo` opens the fixture repository in the normal interactive app.
`dunkr-snapshots` compares generated SVGs with committed baselines and exits
nonzero on a visual change. `--update` is the only operation allowed to replace
baselines.

An optional preview command or test helper renders current SVGs to PNG files
under `artifacts/screenshots/`. That directory is ignored by Git. The
`--preview` command creates those PNGs from the current SVG captures. PNGs are
for human and agent inspection only; SVGs are the test oracle.
On macOS, the preview command uses the built-in `sips` converter; the visual
test oracle itself has no additional dependency.

## Testing

Behavioral tests verify that the long document contains every fixture file in
input order, that sidebar selection moves the vertical scroll position to the
matching section, that manual selection does not replace the document, and that
empty/sidebar-hidden behavior remains correct.

Visual tests capture the four named states and compare normalized SVG output to
the committed baselines. The update command is tested to ensure it requires an
explicit `--update` flag before writing any baseline.

## Success Criteria

1. `uv run dunkr-demo` opens one UI that exposes every fixture change through
   the sidebar and the long diff document.
2. Every fixture file appears exactly once in the document in diff order.
3. Sidebar navigation scrolls to the correct file section without replacing
   the document.
4. `uv run dunkr-snapshots` passes against the committed SVG baselines.
5. A deliberate visual change fails the corresponding snapshot test until
   `uv run dunkr-snapshots --update` is run.
6. Preview PNGs are inspectable but untracked.
