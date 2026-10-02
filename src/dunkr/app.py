"""Native Textual application for browsing rich file diffs."""

from pathlib import Path
from typing import Any

from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from textual import events, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.geometry import Size
from textual.widget import Widget
from textual.widgets import Footer, Header, Static, Tree
from textual.widgets.tree import TreeNode
from textual.worker import Worker

from dunkr.models import ChangeKind, DiffFile, DiffSet, parse_diff
from dunkr.rendering import (
    render_file_hunks,
)


class FileSidebar(Tree[int]):
    """Select a changed file from the parsed diff directory tree."""

    def __init__(self, files: tuple[DiffFile, ...]) -> None:
        """Configure directory tree for changed files and subtrees."""
        self.files = files
        self.file_nodes: list[TreeNode[int]] = []
        total_additions = sum(file.additions for file in files)
        total_deletions = sum(file.deletions for file in files)
        root_label = Text.assemble(
            "Files",
            "  ",
            (f"+{total_additions}", "green"),
            " ",
            (f"-{total_deletions}", "red"),
        )
        super().__init__(root_label, id="files", data=0 if files else None)
        self.show_root = True

    def on_mount(self) -> None:
        """Populate tree nodes for nested subtrees and files once mounted."""
        self.root.expand()
        dir_stats: dict[str, dict[str, int]] = {}
        for index, file in enumerate(self.files):
            parts = file.path.split("/")
            current_path = ""
            for part in parts[:-1]:
                current_path = f"{current_path}/{part}" if current_path else part
                if current_path not in dir_stats:
                    dir_stats[current_path] = {
                        "additions": 0,
                        "deletions": 0,
                        "first_index": index,
                    }
                dir_stats[current_path]["additions"] += file.additions
                dir_stats[current_path]["deletions"] += file.deletions

        nodes: dict[str, TreeNode[int]] = {"": self.root}
        for index, file in enumerate(self.files):
            parts = file.path.split("/")
            current_path = ""
            for part in parts[:-1]:
                parent_path = current_path
                current_path = f"{current_path}/{part}" if current_path else part
                if current_path not in nodes:
                    parent_node = nodes[parent_path]
                    stats = dir_stats[current_path]
                    dir_label = Text.assemble(
                        part,
                        "  ",
                        (f"+{stats['additions']}", "green"),
                        " ",
                        (f"-{stats['deletions']}", "red"),
                    )
                    dir_node = parent_node.add(
                        dir_label, expand=True, data=stats["first_index"]
                    )
                    nodes[current_path] = dir_node

            filename = parts[-1]
            parent_node = nodes[current_path]
            label = Text.assemble(
                filename,
                "  ",
                (f"+{file.additions}", "green"),
                " ",
                (f"-{file.deletions}", "red"),
            )
            leaf = parent_node.add_leaf(label, data=index)
            self.file_nodes.append(leaf)

    @property
    def index(self) -> int | None:
        """Return the index of the currently highlighted file node."""
        if self.cursor_node is not None and self.cursor_node.data is not None:
            return self.cursor_node.data
        return None

    @index.setter
    def index(self, value: int | None) -> None:
        """Highlight the file node corresponding to ``value``."""
        if value is not None and 0 <= value < len(self.file_nodes):
            node = self.file_nodes[value]
            self.select_node(node)


class CodeDocumentWidget(Widget):
    """Render full document code table for one side with auto content width."""

    DEFAULT_CSS = "CodeDocumentWidget { width: auto; height: auto; }"

    def __init__(self, table: Table, width: int) -> None:
        """Store the pre-rendered table and its natural content width."""
        super().__init__()
        self.table = table
        self.needed_width = width

    def get_content_width(self, container: Size, viewport: Size) -> int:
        """Return the wider of the container width and the table's natural content width."""
        return max(container.width, self.needed_width)

    def render(self) -> Table:
        """Set the table width to the actual widget width before handing to Rich."""
        self.table.width = self.size.width
        return self.table

    def on_resize(self, event: events.Resize) -> None:
        """Re-render when the widget is resized so table.width stays in sync."""
        self.refresh()


class LeftPane(ScrollableContainer):
    """Left side code container with independent horizontal scroll and hidden scrollbar."""

    DEFAULT_CSS = """
    LeftPane {
        width: 1fr;
        height: auto;
        overflow-x: auto;
        overflow-y: hidden;
        scrollbar-size: 0 0;
        border-right: solid #2a2c24;
    }
    """


class RightPane(ScrollableContainer):
    """Right side code container with independent horizontal scroll and hidden scrollbar."""

    DEFAULT_CSS = """
    RightPane {
        width: 1fr;
        height: auto;
        overflow-x: auto;
        overflow-y: hidden;
        scrollbar-size: 0 0;
    }
    """


class StatusBannerWidget(Widget):
    """Render a 3-line 100%-wide status banner embedded inside diagonal line shading."""

    DEFAULT_CSS = "StatusBannerWidget { width: 1fr; height: 3; }"

    def __init__(self, text: str, label_style: str, shade_style: str) -> None:
        """Store banner text and style tokens for rendering."""
        super().__init__()
        self.banner_text = text
        self.label_style = label_style
        self.shade_style = shade_style

    def render(self) -> Text:
        """Build a three-line diagonal-shaded banner centred on the banner text."""
        width = max(30, self.size.width)
        label = f"   {self.banner_text}   "
        shade_len = max(0, width - len(label))
        left_shade = shade_len // 2
        right_shade = width - len(label) - left_shade

        res = Text()
        res.append("╲" * width + "\n", style=self.shade_style)
        res.append("╲" * left_shade, style=self.shade_style)
        res.append(label, style=self.label_style)
        res.append("╲" * right_shade + "\n", style=self.shade_style)
        res.append("╲" * width, style=self.shade_style)
        return res


class HunkWidget(Vertical):
    """Compose one diff hunk: a full-width header banner above left/right code panes."""

    DEFAULT_CSS = "HunkWidget { width: 1fr; height: auto; }"

    def __init__(
        self,
        hunk_hdr: Text,
        left_nums: Text,
        left_table: Table,
        left_w: int,
        right_nums: Text,
        right_table: Table,
        right_w: int,
    ) -> None:
        """Store pre-rendered hunk data for compose-time layout."""
        super().__init__(classes="hunk-widget")
        self.hunk_hdr = hunk_hdr
        self.left_nums = left_nums
        self.left_table = left_table
        self.left_w = left_w
        self.right_nums = right_nums
        self.right_table = right_table
        self.right_w = right_w

    def compose(self) -> ComposeResult:
        """Yield the hunk header banner then the side-by-side code row."""
        yield Static(self.hunk_hdr, classes="hunk-header-banner")
        with Horizontal(classes="file-panes-row"):
            with LeftPane():
                yield Static(self.left_nums, classes="nums-column")
                yield CodeDocumentWidget(self.left_table, self.left_w)
            with RightPane():
                yield Static(self.right_nums, classes="nums-column")
                yield CodeDocumentWidget(self.right_table, self.right_w)


class FileSectionWidget(Vertical):
    """Render a single file section: title header, status banners, and async code panes."""

    DEFAULT_CSS = """
    FileSectionWidget {
        width: 1fr;
        height: auto;
    }
    .file-title-header {
        width: 1fr;
        height: auto;
        margin-top: 1;
    }
    .hunk-header-banner {
        width: 1fr;
        height: 1;
        content-align: center middle;
        background: #0f171e;
    }
    .file-panes-row {
        width: 1fr;
        height: auto;
        layout: horizontal;
    }
    .nums-column {
        dock: left;
        width: 6;
        height: 100%;
        background: #0d0f0b;
    }
    """

    def __init__(self, file: DiffFile, index: int) -> None:
        """Store file metadata and assign a stable DOM id for scroll targeting."""
        super().__init__(id=f"section-{index}", classes="file-section")
        self.file = file

    def compose(self) -> ComposeResult:
        """Yield the file header and status banners immediately; hunks load async."""
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

        yield Static(Rule(header_text, style="#3e4036"), classes="file-title-header")

        if self.file.kind is ChangeKind.BINARY:
            yield StatusBannerWidget("Binary file", "bold white on #1c2c3e", "#1c2c3e")
            return

        if self.file.kind is ChangeKind.RENAMED:
            s_name = self.file.source_display_path or self.file.path
            t_name = self.file.target_display_path or self.file.path
            yield StatusBannerWidget(
                f"Renamed: {s_name} → {t_name}",
                "bold white on #1c3038",
                "#1c3038",
            )

        if self.file.kind is ChangeKind.DELETED:
            yield StatusBannerWidget(
                "File was deleted", "bold white on #3b1f24", "#3b1f24"
            )

    def on_mount(self) -> None:
        """Kick off this file's background render worker immediately on mount."""
        if self.file.kind is not ChangeKind.BINARY:
            self._render_hunks()

    @work(thread=True)
    def _render_hunks(self) -> list[Any]:
        """Compute hunk renderables in a background thread."""
        return render_file_hunks(self.file)

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Mount HunkWidgets once the background render worker completes."""
        from textual.worker import WorkerState

        if event.state is WorkerState.SUCCESS and event.worker.result is not None:
            self.mount_hunks(event.worker.result)

    def mount_hunks(self, hunks: list[Any]) -> None:
        """Mount pre-rendered HunkWidgets into this section."""
        hunk_widgets = [
            HunkWidget(
                hunk_hdr=hunk_hdr,
                left_nums=left_nums,
                left_table=left_table,
                left_w=left_w,
                right_nums=right_nums,
                right_table=right_table,
                right_w=right_w,
            )
            for hunk_hdr, (left_nums, left_table, left_w), (
                right_nums,
                right_table,
                right_w,
            ) in hunks
        ]
        if hunk_widgets:
            self.mount(*hunk_widgets)


class DiffView(Vertical):
    """Display every changed file in a single scrollable vertical document."""

    DEFAULT_CSS = """
    DiffView {
        width: 1fr;
        height: 1fr;
    }
    #diff-scroll {
        width: 1fr;
        height: 1fr;
        overflow-x: hidden;
        overflow-y: scroll;
        scrollbar-size: 1 1;
    }
    """

    def __init__(self, files: tuple[DiffFile, ...]) -> None:
        """Initialize DiffView with the ordered file list."""
        super().__init__(id="diff-view")
        self.files = files

    def compose(self) -> ComposeResult:
        """Compose a single vertical scroll container with one section per file."""
        with ScrollableContainer(id="diff-scroll"):
            for index, file in enumerate(self.files):
                yield FileSectionWidget(file, index)


class DunkrApp(App[None]):
    """Browse a parsed Git diff by changed file."""

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("ctrl+c", "quit", "Quit"),
        ("f", "toggle_sidebar", "Files"),
    ]
    """Keyboard controls for quitting and toggling the file sidebar."""

    CSS = """
    Screen { background: #0d0f0b; }
    #body { height: 1fr; }
    #files {
        width: 34;
        min-width: 24;
        border-right: solid #2a2c24;
        background: #0d0f0b;
        color: #c5c8c6;
        overflow-x: auto;
    }
    #files:focus {
        background: #0d0f0b;
    }
    #files > .tree--guides {
        color: #3e4036;
    }
    #files > .tree--cursor {
        background: #252820;
        color: #ffffff;
        text-style: bold;
    }
    #empty { width: 1fr; height: 1fr; content-align: center middle; }
    .sidebar-hidden #files { display: none; }
    """
    """Layout and minimal dark presentation for the diff browser."""

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
            with Horizontal(id="body", classes="sidebar-hidden"):
                yield FileSidebar(files=self.diff_set.files)
                yield DiffView(files=self.diff_set.files)
        yield Footer()

    def on_mount(self) -> None:
        """Select the first changed file without replacing the document."""
        self.title = "dunkr"
        if self.diff_set.files:
            sidebar = self.query_one(FileSidebar)
            sidebar.index = 0
            self.call_after_refresh(self._scroll_to_file, 0)

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted[int]) -> None:
        """Scroll the document when a file node is highlighted in the sidebar."""
        if event.node.data is not None:
            self.call_after_refresh(self._scroll_to_file, event.node.data)

    def on_tree_node_selected(self, event: Tree.NodeSelected[int]) -> None:
        """Scroll the document when a file node is selected in the sidebar."""
        if event.node.data is not None:
            self.call_after_refresh(self._scroll_to_file, event.node.data)

    def _scroll_to_file(self, index: int) -> None:
        """Scroll the diff viewport so the target section header is visible."""
        try:
            section = self.query_one(f"#section-{index}", FileSectionWidget)
            scroll = self.query_one("#diff-scroll", ScrollableContainer)
            scroll.scroll_to_widget(section, animate=False)
        except Exception:
            pass

    def action_toggle_sidebar(self) -> None:
        """Toggle the file sidebar without changing selection."""
        if self.diff_set.files:
            self.query_one("#body").toggle_class("sidebar-hidden")
