# dunkr

A rich, interactive side-by-side Git diff viewer built with Textual.

## Usage

```console
git diff | dunkr
dunkr
```

Pipe a unified diff to `dunkr`, or run it without a pipe to view the current
working-tree diff. Use the file sidebar or mouse to select a change, scroll the
diff normally, press `b` to toggle the sidebar, and press `q` to quit. `dunkr`
is read-only.
