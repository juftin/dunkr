"""Native Textual application for browsing rich file diffs."""

from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
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


class DiffView(Static):
    """Display one selected file as a native Rich renderable."""

    def show_file(self, file: DiffFile) -> None:
        """Replace the pane content with ``file``."""
        self.update(FileDiffRenderable(file=file))


class DunkrApp(App[None]):
    """Browse a parsed Git diff by changed file."""

    BINDINGS = [("q", "quit", "Quit"), ("b", "toggle_sidebar", "Files")]
    """Keyboard controls for quitting and toggling the file sidebar."""

    CSS = """
    Screen { background: #0d0f0b; }
    #body { height: 1fr; }
    #files { width: 32; min-width: 20; border-right: solid #3e4036; }
    #diff-scroll { width: 1fr; }
    #diff { width: 1fr; }
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
            with Horizontal(id="body"):
                yield FileSidebar(files=self.diff_set.files)
                with VerticalScroll(id="diff-scroll"):
                    yield DiffView(id="diff")
        yield Footer()

    def on_mount(self) -> None:
        """Select and display the first changed file."""
        self.title = "dunkr"
        if self.diff_set.files:
            sidebar = self.query_one(FileSidebar)
            sidebar.index = 0
            self.query_one(DiffView).show_file(self.diff_set.files[0])

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Display the file corresponding to the highlighted sidebar row."""
        if event.list_view.id == "files" and event.list_view.index is not None:
            self.query_one(DiffView).show_file(
                self.diff_set.files[event.list_view.index]
            )
            self.query_one("#diff-scroll", VerticalScroll).scroll_home(animate=False)

    def action_toggle_sidebar(self) -> None:
        """Toggle the file sidebar without changing selection."""
        if self.diff_set.files:
            self.query_one("#body").toggle_class("sidebar-hidden")
