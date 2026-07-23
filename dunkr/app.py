"""Native Textual application for browsing rich file diffs."""

from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
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


class DiffView(Vertical):
    """Display every changed file as one ordered vertical document."""

    def __init__(self, files: tuple[DiffFile, ...]) -> None:
        """Store every parsed file for composition as stable document sections."""
        self.files = files
        super().__init__(id="diff")

    def compose(self) -> ComposeResult:
        """Yield each file's native Rich diff in input order."""
        for index, file in enumerate(self.files):
            yield Static(
                FileDiffRenderable(file=file),
                id=f"section-{index}",
                classes="file-section",
            )


class DunkrApp(App[None]):
    """Browse a parsed Git diff by changed file."""

    BINDINGS = [("q", "quit", "Quit"), ("b", "toggle_sidebar", "Files")]
    """Keyboard controls for quitting and toggling the file sidebar."""

    CSS = """
    Screen { background: #0d0f0b; }
    #body { height: 1fr; }
    #files { width: 32; min-width: 20; border-right: solid #3e4036; }
    #diff-scroll { width: 1fr; }
    #diff { width: 1fr; height: auto; }
    .file-section { width: 1fr; height: auto; }
    #empty { width: 1fr; height: 1fr; content-align: center middle; }
    .sidebar-hidden #files { display: none; }
    """
    """Layout and minimal dark presentation for the diff browser."""

    def __init__(self, diff: str, project_root: Path) -> None:
        """Parse ``diff`` once and initialize selected-file state."""
        super().__init__()
        self.diff_set: DiffSet = parse_diff(text=diff, project_root=project_root)
        self.section_offsets: dict[str, int] = {}
        """Current vertical offsets for document file sections, by display path."""

    def compose(self) -> ComposeResult:
        """Compose app chrome, file selection, and scrollable diff content."""
        yield Header(show_clock=False)
        if not self.diff_set.files:
            yield Static("No changes", id="empty")
        else:
            with Horizontal(id="body"):
                yield FileSidebar(files=self.diff_set.files)
                with VerticalScroll(id="diff-scroll"):
                    yield DiffView(files=self.diff_set.files)
        yield Footer()

    def on_mount(self) -> None:
        """Select the first changed file without replacing the document."""
        self.title = "dunkr"
        if self.diff_set.files:
            sidebar = self.query_one(FileSidebar)
            sidebar.index = 0
            self.call_after_refresh(self._scroll_to_file, 0)

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Scroll the stable document to the highlighted file section."""
        if event.list_view.id == "files" and event.list_view.index is not None:
            self.call_after_refresh(self._scroll_to_file, event.list_view.index)

    def _scroll_to_file(self, index: int) -> None:
        """Move the document viewport to a section after the layout is current."""
        file = self.diff_set.files[index]
        section = self.query_one(f"#section-{index}")
        scroll = self.query_one("#diff-scroll", VerticalScroll)
        scroll.scroll_to_widget(section, top=True, animate=False, immediate=True)
        self.section_offsets[file.path] = int(scroll.scroll_offset.y)

    def action_toggle_sidebar(self) -> None:
        """Toggle the file sidebar without changing selection."""
        if self.diff_set.files:
            self.query_one("#body").toggle_class("sidebar-hidden")
