"""Native Rich rendering for one selected diff file."""

from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
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
        additions_str = (
            "1 addition"
            if self.file.additions == 1
            else f"{self.file.additions} additions"
        )
        deletions_str = (
            "1 removal"
            if self.file.deletions == 1
            else f"{self.file.deletions} removals"
        )
        header_text = Text()
        header_text.append(self.file.path, style="bold white")
        header_text.append(" (", style="dim")
        header_text.append(additions_str, style="bold green")
        header_text.append(", ", style="dim")
        header_text.append(deletions_str, style="bold red")
        header_text.append(")", style="dim")
        yield Rule(header_text, style="#3e4036")

        if self.file.kind is ChangeKind.BINARY:
            yield Text("Binary file", style="bold blue", justify="center")
            return
        if self.file.kind is ChangeKind.DELETED:
            yield Text("File was deleted", style="bold red", justify="center")
        elif self.file.kind is ChangeKind.RENAMED:
            source_name = self.file.source_display_path or self.file.path
            target_name = self.file.target_display_path or self.file.path
            yield Text(
                f"Renamed: {source_name} → {target_name}",
                style="cyan",
                justify="center",
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


@lru_cache(maxsize=4096)
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


@lru_cache(maxsize=64)
def _get_syntax(lexer: str) -> Syntax:
    """Return a reusable ``Syntax`` object backed by a cached Pygments lexer instance.

    Passing a Pygments *instance* (not a string) to ``Syntax.__init__`` means
    ``Syntax.highlight()`` uses the cached object directly and never calls the
    expensive ``get_lexer_by_name()`` on each invocation.

    Parameters
    ----------
    lexer:
        Pygments lexer alias (e.g. ``"python"``, ``"xml"``).

    Returns
    -------
    Syntax:
        A single shared ``Syntax`` instance; ``highlight()`` is stateless so
        reuse is safe.
    """
    from pygments.lexers import get_lexer_by_name

    try:
        lexer_instance = get_lexer_by_name(lexer)
    except ClassNotFound:
        lexer_instance = get_lexer_by_name("text")
    return Syntax("", lexer=lexer_instance)


@lru_cache(maxsize=4096)
def _highlight_line(value: str, lexer: str) -> Text:
    """Syntax-highlight one source line, caching the result by content and lexer.

    Lines longer than 500 characters (SVG paths, base64 blobs, minified JS)
    are returned as plain text — they are unreadable as syntax and extremely
    expensive for Pygments to tokenise.

    Parameters
    ----------
    value:
        The raw source line (already stripped of trailing newline).
    lexer:
        Pygments lexer alias (e.g. ``"python"``, ``"text"``).

    Returns
    -------
    Text:
        A Rich ``Text`` object with syntax spans applied, trailing whitespace stripped.
    """
    if len(value) > 500:
        return Text(value)
    result = _get_syntax(lexer).highlight(value)
    result.rstrip()
    return result


def _code_cell(
    *,
    line: Line | None,
    line_number: int | None,
    lexer: str,
    background: str | None,
    emphasis_background: str,
    ranges: tuple[tuple[int, int], ...],
    col_width: int,
    include_line_number: bool = True,
) -> Text:
    """Build one independently numbered, syntax-highlighted code cell."""
    if line is None:
        empty_cell = Text(" " * col_width)
        return empty_cell

    num_style = (
        Style(color="#98e024", bold=True)
        if background == "#183c2b"
        else Style(color="#f4005f", bold=True)
        if background == "#3b1f24"
        else Style(color="#555555")
    )
    num_text = Text(f"{line_number or '':>4} ", style=num_style)

    value = line.value.rstrip("\n")
    code = _highlight_line(value, lexer).copy()
    for start, end in ranges:
        code.stylize(
            Style(bold=True, bgcolor=emphasis_background), start=start, end=end
        )

    cell = Text.assemble(num_text, code) if include_line_number else code
    # Pad to max(col_width, 500) so background colours fill the full pane
    # even when the file's lines are shorter than the container width.
    cell.pad_right(max(col_width, 500))
    if background is not None:
        cell.stylize(Style(bgcolor=background))
    return cell


def _side_content_widths(file: DiffFile) -> tuple[int, int]:
    """Return the max column widths needed for left and right sides independently."""
    left_max = 0
    right_max = 0
    for hunk in file.patch:
        for source, target in _paired_rows(hunk):
            if source and source.value:
                left_max = max(left_max, len(source.value.rstrip("\n")))
            if target and target.value:
                right_max = max(right_max, len(target.value.rstrip("\n")))
    # Cap at a terminal-reasonable maximum — a single minified/SVG line can be
    # tens of thousands of characters, which makes every empty opposite-pane cell
    # an enormous string allocation.
    _MAX_COL = 2000
    return min(left_max + 6, _MAX_COL), min(right_max + 6, _MAX_COL)


def _render_left_hunk(hunk: Hunk, lexer: str, col_width: int) -> tuple[Text, Table]:
    """Render the left (before/deletions) side line numbers and code table of a hunk."""
    nums_text = Text()
    table = Table.grid(expand=True)
    table.add_column(overflow="crop", no_wrap=True)

    for source, target in _paired_rows(hunk):
        lno = source.source_line_no if source is not None else None
        num_style = (
            Style(color="#f4005f", bold=True)
            if source is not None and source.is_removed
            else Style(color="#555555")
        )
        if lno is not None:
            nums_text.append(f"{lno:>4} \n", style=num_style)
        else:
            nums_text.append("     \n")

        source_value = source.value.rstrip("\n") if source is not None else ""
        target_value = target.value.rstrip("\n") if target is not None else ""
        # Skip intraline diff when there is no paired line (pure deletion) or
        # when both sides are identical context lines — ranges would be empty.
        if source is not None and target is not None and source_value != target_value:
            source_ranges, _ = _changed_ranges(source_value, target_value)
        else:
            source_ranges = ()
        table.add_row(
            _code_cell(
                line=source,
                line_number=lno,
                lexer=lexer,
                background="#3b1f24"
                if source is not None and source.is_removed
                else None,
                emphasis_background="#6b3340",
                ranges=source_ranges,
                col_width=col_width,
                include_line_number=False,
            )
        )
    return nums_text, table


def _render_right_hunk(hunk: Hunk, lexer: str, col_width: int) -> tuple[Text, Table]:
    """Render the right (after/additions) side line numbers and code table of a hunk."""
    nums_text = Text()
    table = Table.grid(expand=True)
    table.add_column(overflow="crop", no_wrap=True)

    for source, target in _paired_rows(hunk):
        lno = target.target_line_no if target is not None else None
        num_style = (
            Style(color="#98e024", bold=True)
            if target is not None and target.is_added
            else Style(color="#555555")
        )
        if lno is not None:
            nums_text.append(f"{lno:>4} \n", style=num_style)
        else:
            nums_text.append("     \n")

        source_value = source.value.rstrip("\n") if source is not None else ""
        target_value = target.value.rstrip("\n") if target is not None else ""
        # Skip intraline diff when there is no paired line (pure addition) or
        # when both sides are identical context lines — ranges would be empty.
        if source is not None and target is not None and source_value != target_value:
            _, target_ranges = _changed_ranges(source_value, target_value)
        else:
            target_ranges = ()
        table.add_row(
            _code_cell(
                line=target,
                line_number=lno,
                lexer=lexer,
                background="#183c2b"
                if target is not None and target.is_added
                else None,
                emphasis_background="#245a3e",
                ranges=target_ranges,
                col_width=col_width,
                include_line_number=False,
            )
        )
    return nums_text, table


def render_file_hunks(
    file: DiffFile,
) -> list[tuple[Text, tuple[Text, Table, int], tuple[Text, Table, int]]]:
    """Render separate hunk headers and code tables for each hunk in a file."""
    hunks_rendered: list[
        tuple[Text, tuple[Text, Table, int], tuple[Text, Table, int]]
    ] = []
    left_w, right_w = _side_content_widths(file)

    try:
        lexer = Syntax.guess_lexer(file.target_display_path or file.path)
    except ClassNotFound:
        lexer = "text"

    for hunk in file.patch:
        hunk_header = Text(justify="center")
        hunk_header.append("@@ ", style="dim cyan")
        hunk_header.append(f"-{hunk.source_start},{hunk.source_length}", style="red")
        hunk_header.append(" ")
        hunk_header.append(f"+{hunk.target_start},{hunk.target_length}", style="green")
        hunk_header.append(" @@", style="dim cyan")
        if hunk.section_header:
            hunk_header.append(f" {hunk.section_header}", style="dim white")

        left_nums = Text()
        left_table = Table.grid(expand=True)
        left_table.width = left_w
        left_table.add_column(width=left_w, overflow="ignore", no_wrap=True)

        right_nums = Text()
        right_table = Table.grid(expand=True)
        right_table.width = right_w
        right_table.add_column(width=right_w, overflow="ignore", no_wrap=True)

        for source, target in _paired_rows(hunk):
            l_no = source.source_line_no if source is not None else None
            r_no = target.target_line_no if target is not None else None

            if l_no is not None:
                left_nums.append(
                    f"{l_no:4d} \n",
                    style=(
                        "red"
                        if source is not None and source.is_removed
                        else "dim white"
                    ),
                )
            else:
                left_nums.append("     \n")

            if r_no is not None:
                right_nums.append(
                    f"{r_no:4d} \n",
                    style=(
                        "green"
                        if target is not None and target.is_added
                        else "dim white"
                    ),
                )
            else:
                right_nums.append("     \n")

            s_val = source.value.rstrip("\n") if source is not None else ""
            t_val = target.value.rstrip("\n") if target is not None else ""
            sr, tr = _changed_ranges(s_val, t_val)

            left_table.add_row(
                _code_cell(
                    line=source,
                    line_number=l_no,
                    lexer=lexer,
                    background=(
                        "#3b1f24" if source is not None and source.is_removed else None
                    ),
                    emphasis_background="#6b3340",
                    ranges=sr,
                    col_width=left_w,
                    include_line_number=False,
                )
            )
            right_table.add_row(
                _code_cell(
                    line=target,
                    line_number=r_no,
                    lexer=lexer,
                    background=(
                        "#183c2b" if target is not None and target.is_added else None
                    ),
                    emphasis_background="#245a3e",
                    ranges=tr,
                    col_width=right_w,
                    include_line_number=False,
                )
            )

        hunks_rendered.append(
            (
                hunk_header,
                (left_nums, left_table, left_w),
                (right_nums, right_table, right_w),
            )
        )

    return hunks_rendered


def build_full_document_panes(
    files: tuple[DiffFile, ...],
) -> tuple[
    tuple[Text, Table, int],
    tuple[Text, Table, int],
    dict[str, int],
]:
    """Build left and right pane renderables and line offsets for the full document."""
    left_nums = Text()
    left_table = Table.grid(expand=True)

    right_nums = Text()
    right_table = Table.grid(expand=True)

    max_left_w = 0
    max_right_w = 0
    for file in files:
        lw, rw = _side_content_widths(file)
        max_left_w = max(max_left_w, lw)
        max_right_w = max(max_right_w, rw)

    max_left_w = max(24, max_left_w)
    max_right_w = max(24, max_right_w)

    left_table.width = max_left_w
    left_table.add_column(width=max_left_w, overflow="ignore", no_wrap=True)

    right_table.width = max_right_w
    right_table.add_column(width=max_right_w, overflow="ignore", no_wrap=True)

    section_offsets: dict[str, int] = {}
    current_line = 0

    for index, file in enumerate(files):
        section_offsets[file.path] = current_line
        additions_str = (
            "1 addition" if file.additions == 1 else f"{file.additions} additions"
        )
        deletions_str = (
            "1 removal" if file.deletions == 1 else f"{file.deletions} removals"
        )

        left_hdr = Text()
        left_hdr.append(file.path, style="bold white")
        left_hdr.append(" ", style="dim")

        right_hdr = Text()
        right_hdr.append("(", style="dim")
        right_hdr.append(additions_str, style="bold green")
        right_hdr.append(", ", style="dim")
        right_hdr.append(deletions_str, style="bold red")
        right_hdr.append(")", style="dim")
        right_hdr.append(" ", style="dim")

        left_nums.append("     \n", style="dim cyan")
        left_table.add_row(Rule(left_hdr, style="#3e4036", align="right"))

        right_nums.append("     \n", style="dim cyan")
        right_table.add_row(Rule(right_hdr, style="#3e4036", align="left"))
        current_line += 1

        if file.kind is ChangeKind.BINARY:
            left_nums.append("     \n")
            left_table.add_row(Text("Binary file", style="bold blue", justify="center"))
            right_nums.append("     \n")
            right_table.add_row(
                Text("Binary file", style="bold blue", justify="center")
            )
            current_line += 1
            continue
        elif file.kind is ChangeKind.DELETED:
            left_nums.append("     \n")
            left_table.add_row(
                Text("File was deleted", style="bold red", justify="center")
            )
            right_nums.append("     \n")
            right_table.add_row(
                Text("File was deleted", style="bold red", justify="center")
            )
            current_line += 1
        elif file.kind is ChangeKind.RENAMED:
            s_name = file.source_display_path or file.path
            t_name = file.target_display_path or file.path
            left_nums.append("     \n")
            left_table.add_row(
                Text(
                    f"Renamed: {s_name} → {t_name}",
                    style="cyan",
                    justify="center",
                )
            )
            right_nums.append("     \n")
            right_table.add_row(
                Text(
                    f"Renamed: {s_name} → {t_name}",
                    style="cyan",
                    justify="center",
                )
            )
            current_line += 1
            if len(file.patch) == 0:
                continue

        try:
            lexer = Syntax.guess_lexer(file.target_display_path or file.path)
        except ClassNotFound:
            lexer = "text"

        for hunk in file.patch:
            hunk_header = Text(justify="center")
            hunk_header.append("@@ ", style="dim cyan")
            hunk_header.append(
                f"-{hunk.source_start},{hunk.source_length}", style="red"
            )
            hunk_header.append(" ")
            hunk_header.append(
                f"+{hunk.target_start},{hunk.target_length}", style="green"
            )
            hunk_header.append(" @@", style="dim cyan")
            if hunk.section_header:
                hunk_header.append(f" {hunk.section_header}", style="dim white")

            left_nums.append("     \n", style="dim cyan")
            left_table.add_row(hunk_header)
            right_nums.append("     \n", style="dim cyan")
            right_table.add_row(hunk_header)
            current_line += 1

            for source, target in _paired_rows(hunk):
                l_no = source.source_line_no if source is not None else None
                r_no = target.target_line_no if target is not None else None

                if l_no is not None:
                    left_nums.append(
                        f"{l_no:4d} \n",
                        style=(
                            "red"
                            if source is not None and source.is_removed
                            else "dim white"
                        ),
                    )
                else:
                    left_nums.append("     \n")

                if r_no is not None:
                    right_nums.append(
                        f"{r_no:4d} \n",
                        style=(
                            "green"
                            if target is not None and target.is_added
                            else "dim white"
                        ),
                    )
                else:
                    right_nums.append("     \n")

                s_val = source.value.rstrip("\n") if source is not None else ""
                t_val = target.value.rstrip("\n") if target is not None else ""
                sr, tr = _changed_ranges(s_val, t_val)

                left_table.add_row(
                    _code_cell(
                        line=source,
                        line_number=l_no,
                        lexer=lexer,
                        background=(
                            "#3b1f24"
                            if source is not None and source.is_removed
                            else None
                        ),
                        emphasis_background="#6b3340",
                        ranges=sr,
                        col_width=max_left_w,
                        include_line_number=False,
                    )
                )
                right_table.add_row(
                    _code_cell(
                        line=target,
                        line_number=r_no,
                        lexer=lexer,
                        background=(
                            "#183c2b"
                            if target is not None and target.is_added
                            else None
                        ),
                        emphasis_background="#245a3e",
                        ranges=tr,
                        col_width=max_right_w,
                        include_line_number=False,
                    )
                )
                current_line += 1

    return (
        (left_nums, left_table, max_left_w),
        (right_nums, right_table, max_right_w),
        section_offsets,
    )


def _render_hunks(file: DiffFile, width: int) -> Iterable[object]:
    """Yield width-aware side-by-side tables for every hunk without wrapping."""
    try:
        lexer = Syntax.guess_lexer(file.target_display_path or file.path)
    except ClassNotFound:
        lexer = "text"
    left_needed, right_needed = _side_content_widths(file)
    half_width = max(1, width // 2)
    left_col_width = max(half_width, left_needed)
    right_col_width = max(half_width, right_needed)

    for hunk in file.patch:
        hunk_header = Text(justify="center")
        hunk_header.append("@@ ", style="dim cyan")
        hunk_header.append(f"-{hunk.source_start},{hunk.source_length}", style="red")
        hunk_header.append(" ")
        hunk_header.append(f"+{hunk.target_start},{hunk.target_length}", style="green")
        hunk_header.append(" @@", style="dim cyan")
        if hunk.section_header:
            hunk_header.append(f" {hunk.section_header}", style="dim white")
        yield hunk_header

        left_table = Table.grid(expand=True)
        left_table.width = left_col_width
        left_table.add_column(width=left_col_width, overflow="ignore", no_wrap=True)

        right_table = Table.grid(expand=True)
        right_table.width = right_col_width
        right_table.add_column(width=right_col_width, overflow="ignore", no_wrap=True)

        for source, target in _paired_rows(hunk):
            source_value = source.value.rstrip("\n") if source is not None else ""
            target_value = target.value.rstrip("\n") if target is not None else ""
            source_ranges, target_ranges = _changed_ranges(source_value, target_value)

            left_table.add_row(
                _code_cell(
                    line=source,
                    line_number=(source.source_line_no if source is not None else None),
                    lexer=lexer,
                    background=(
                        "#3b1f24" if source is not None and source.is_removed else None
                    ),
                    emphasis_background="#6b3340",
                    ranges=source_ranges,
                    col_width=left_col_width,
                    include_line_number=True,
                )
            )
            right_table.add_row(
                _code_cell(
                    line=target,
                    line_number=(target.target_line_no if target is not None else None),
                    lexer=lexer,
                    background=(
                        "#183c2b" if target is not None and target.is_added else None
                    ),
                    emphasis_background="#245a3e",
                    ranges=target_ranges,
                    col_width=right_col_width,
                    include_line_number=True,
                )
            )

        hunk_grid = Table.grid(expand=True)
        hunk_grid.width = left_col_width + right_col_width
        hunk_grid.add_column(width=left_col_width, overflow="ignore", no_wrap=True)
        hunk_grid.add_column(width=right_col_width, overflow="ignore", no_wrap=True)
        hunk_grid.add_row(left_table, right_table)
        yield hunk_grid
