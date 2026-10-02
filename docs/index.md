<h1 align="center">dunkr</h1>

<p align="center">
the spiritual successor to dunk
</p>

<p align="center">
  <a href="https://github.com/juftin/dunkr"><img src="https://img.shields.io/github/v/release/juftin/dunkr?color=blue&label=dunkr&logo=github" alt="GitHub"></a>
  <a href="https://pypi.python.org/pypi/dunkr/"><img src="https://img.shields.io/pypi/pyversions/dunkr?label=PyPI&logo=python" alt="PyPI"></a>
  <a href="https://github.com/juftin/dunkr/blob/main/LICENSE"><img src="https://img.shields.io/github/license/juftin/dunkr?color=blue&label=License" alt="GitHub License"></a>
  <a href="https://github.com/juftin/dunkr/actions/workflows/test.yaml?query=branch%3Amain"><img src="https://github.com/juftin/dunkr/actions/workflows/test.yaml/badge.svg?branch=main" alt="Testing Status"></a>
  <a href="https://github.com/go-task/task"><img src="https://img.shields.io/badge/task---?message=task&logo=task&color=teal&labelColor=grey" alt="task"></a>
  <a href="https://github.com/astral-sh/uv"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json" alt="uv"></a>
  <a href="https://github.com/pre-commit/pre-commit"><img src="https://img.shields.io/badge/pre--commit-enabled-lightgreen?logo=pre-commit" alt="pre-commit"></a>
  <a href="https://juftin.github.io/dunkr/"><img src="https://img.shields.io/static/v1?message=docs&color=526CFE&logo=Material+for+MkDocs&logoColor=FFFFFF&label=" alt="docs"></a>
  <a href="https://github.com/semantic-release/semantic-release"><img src="https://img.shields.io/badge/%20%20%F0%9F%93%A6%F0%9F%9A%80-semantic--release-e10079.svg" alt="semantic-release"></a>
  <a href="https://gitmoji.dev"><img src="https://img.shields.io/badge/gitmoji-%20😜%20😍-FFDD67.svg" alt="Gitmoji"></a>
</p>

A rich, interactive side-by-side Git diff viewer built with Textual.

## Installation

Install `dunkr` in an isolated environment with [pipx](https://pipx.pypa.io/) or [uv](https://docs.astral.sh/uv/):

```console
uv tool install dunkr
```

or with pipx:

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
diff normally, press `f` to toggle the sidebar, and press `q` or `ctrl+c` to quit. `dunkr`
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
