"""Native Rich rendering for one selected diff file."""

from dataclasses import dataclass
from difflib import SequenceMatcher
from itertools import zip_longest
from typing import Iterable

from pygments.util import ClassNotFound
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
    """Selected file and parsed hunks to render."""

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
        elif self.file.kind is ChangeKind.RENAMED:
            source_name = self.file.source_display_path or self.file.path
            target_name = self.file.target_display_path or self.file.path
            yield Text(
                f"Renamed: {source_name} → {target_name}",
                style="cyan",
            )
            if len(self.file.patch) == 0:
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
        elif line.line_type == "\\":
            continue
        else:
            rows.extend(_flush_changed_lines(removed, added))
            removed.clear()
            added.clear()
            rows.append((line, line))
    rows.extend(_flush_changed_lines(removed, added))
    return rows


def _changed_ranges(
    left: str, right: str
) -> tuple[tuple[tuple[int, int], ...], tuple[tuple[int, int], ...]]:
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
    line_number: int | None,
    lexer: str,
    background: str | None,
    emphasis_background: str,
    ranges: tuple[tuple[int, int], ...],
) -> Text:
    """Build one independently numbered, syntax-highlighted code cell."""
    if line is None:
        return Text()
    value = line.value.rstrip("\n")
    code = Syntax(value, lexer=lexer, word_wrap=True).highlight(value)
    if background is not None:
        code.stylize(Style(bgcolor=background))
    for start, end in ranges:
        code.stylize(
            Style(bold=True, bgcolor=emphasis_background), start=start, end=end
        )
    return Text.assemble((f"{line_number or '':>4} ", "dim"), code)


def _render_hunks(file: DiffFile, width: int) -> Iterable[object]:
    """Yield width-aware side-by-side tables for every hunk."""
    try:
        lexer = Syntax.guess_lexer(file.target_display_path or file.path)
    except ClassNotFound:
        lexer = "text"
    for hunk in file.patch:
        yield Text(
            f"@@ -{hunk.source_start},{hunk.source_length} "
            f"+{hunk.target_start},{hunk.target_length} @@ "
            f"{hunk.section_header or ''}",
            style="dim",
        )
        table = Table.grid(expand=True, padding=(0, 1))
        table.width = max(1, width)
        table.add_column(ratio=1, overflow="fold")
        table.add_column(ratio=1, overflow="fold")
        for source, target in _paired_rows(hunk):
            source_value = source.value.rstrip("\n") if source is not None else ""
            target_value = target.value.rstrip("\n") if target is not None else ""
            source_ranges, target_ranges = _changed_ranges(source_value, target_value)
            table.add_row(
                _code_cell(
                    line=source,
                    line_number=(source.source_line_no if source is not None else None),
                    lexer=lexer,
                    background=(
                        "#3b1f24" if source is not None and source.is_removed else None
                    ),
                    emphasis_background="#6b3340",
                    ranges=source_ranges,
                ),
                _code_cell(
                    line=target,
                    line_number=(target.target_line_no if target is not None else None),
                    lexer=lexer,
                    background=(
                        "#183c2b" if target is not None and target.is_added else None
                    ),
                    emphasis_background="#245a3e",
                    ranges=target_ranges,
                ),
            )
        yield table
