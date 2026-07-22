# Dunkr Textual Viewer Design

## Goal

Replace the `dunk` MRE with `dunkr`, a small, read-only Textual application for browsing a rich side-by-side Git diff. The first version prioritizes a clean native-Textual architecture and a focused viewing experience over advanced diff operations.

## Scope

The first version supports:

- launching as `dunkr`;
- reading a unified diff from piped standard input;
- running `git diff` when standard input is an interactive terminal;
- selecting a changed file from a collapsible sidebar with the keyboard or mouse;
- scrolling a side-by-side diff for the selected file;
- responsive reflow when the terminal is resized;
- quitting with `q`;
- syntax and intraline highlighting;
- clear views for empty diffs, deleted files, renamed files, and binary files; and
- a readable error and nonzero exit status when `git diff` cannot run.

The first version explicitly excludes search, hunk navigation commands, collapsing individual hunks, staging or unstaging, configuration, custom themes, and alternate Git comparison modes.

## Architecture

### Input Boundary

The CLI resolves the diff text before starting Textual:

- If standard input is not a TTY, read the complete unified diff from standard input.
- If standard input is a TTY, execute `git diff` in the current working directory and use its standard output.
- If Git exits unsuccessfully, write its diagnostic to standard error and exit nonzero without launching the app.

This boundary keeps subprocess and terminal concerns out of the UI. It also prevents Textual from inheriting an exhausted pipe as its input source.

### Diff Model

Parse the unified diff once into application-owned file models. Each file model contains the information needed by both the sidebar and diff pane: display path, source and target paths, change type, addition and deletion counts, binary status, and hunks.

The model layer must not depend on Textual widgets or Git subprocess execution. Existing `unidiff` types may be used internally, but UI code consumes the application-owned interface rather than traversing parser objects directly.

### Application Shell

`DunkrApp` owns the parsed diff and the selected-file identity. Its layout contains:

- a collapsible `FileSidebar` built around Textual's selection widgets; and
- a scrollable `DiffView` for the selected file.

Selecting a file emits a Textual message. `DunkrApp` updates its selected-file state and asks `DiffView` to display the corresponding model. The sidebar does not render diffs, and the diff view does not know how the input was obtained.

### Rendering

`DiffView` builds native Rich renderables that Textual can render directly. It must not force terminal output into a string, serialize ANSI control sequences, or reparse ANSI with `Text.from_ansi`.

The selected file renders as a side-by-side source and target presentation with line numbers, syntax highlighting, changed-line backgrounds, and intraline emphasis. Existing highlighting algorithms may be retained when they can operate on Rich segments without terminal serialization.

Only the selected file is rendered, directly from parsed patch content without reading the target working-tree file. This bounds rendering work and makes the sidebar the single file-navigation mechanism.

### Responsive Behavior

Textual owns layout and scrolling. The sidebar has a practical fixed or bounded width and may be collapsed by the user. The diff pane consumes the remaining width. A resize invalidates and rebuilds the selected file's width-dependent renderable without reparsing the full diff.

## User Interaction

- Up and down move through files while the sidebar has focus.
- Enter or a mouse click selects a file.
- Standard Textual scrolling moves through the selected diff.
- `b` toggles the sidebar between collapsed and visible.
- `q` exits the application.

No interaction mutates the repository or index.

## States and Errors

- An empty parsed diff shows a centered `No changes` message instead of an empty sidebar.
- A malformed piped diff exits with a concise parse error.
- Deleted and binary files show descriptive content rather than attempting source-code rendering.
- Pure renames show the old and new paths and indicate that no content changed.
- A failed implicit `git diff` prints Git's diagnostic and exits nonzero.

## Rename

The Python package, console entry point, application class, visible title, and documentation become `dunkr`. The old `dunk` entry point is removed rather than maintained as an alias.

## Testing

Tests are divided by boundary:

- CLI tests verify piped-input selection, implicit `git diff`, and Git failure behavior.
- Model tests verify file metadata for modified, added, deleted, renamed, and binary patches.
- Rendering tests verify changed source and target text, syntax/intraline style application, and special-file states without launching a real terminal.
- Textual pilot tests verify sidebar population, file selection, scrolling layout, the empty state, and resize-triggered reflow.

The control-code regression is enforced structurally: production rendering never round-trips through ANSI text, and piped input is fully resolved before the app starts with terminal input available to Textual.

## Success Criteria

The design is complete when:

1. `git diff | dunkr` and plain `dunkr` open the same native Textual viewer for equivalent input.
2. A user can select any changed file and scroll its rich side-by-side diff.
3. Resizing produces a usable reflowed view.
4. No Rich-to-ANSI-to-Rich conversion exists in the UI path.
5. The viewer performs no repository mutation.
6. Automated tests cover the input, model, rendering, and essential interaction boundaries.
