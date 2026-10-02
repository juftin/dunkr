# dunkr

> the spiritual successor to [dunk](https://github.com/darrenburns/dunk)

A rich, interactive side-by-side Git diff viewer built with Textual.

## Installation

Install `dunkr` in an isolated environment with [pipx](https://pipx.pypa.io/):

```console
pipx install dunkr
```

## Usage

```console
git diff | dunkr
dunkr
```

Pipe a unified diff to `dunkr`, or run it without a pipe to view the current
working-tree diff. Use the file sidebar or mouse to select a change, scroll the
diff normally, press `b` to toggle the sidebar, and press `q` to quit. `dunkr`
is read-only.

## Visual regression checks

The deterministic mixed-diff demo is useful for inspecting the whole interface:

```console
uv run dunkr-demo
uv run dunkr-snapshots
uv run dunkr-snapshots --update
uv run dunkr-snapshots --preview
```

The ordinary snapshot command compares the committed SVG baselines. Only the
explicit `--update` command rewrites them. `--preview` additionally writes
ignored PNGs to `artifacts/screenshots/` for visual inspection.
