"""Tests for the deterministic mixed Git-diff demo."""

from dunkr.demo import create_demo_repository
from dunkr.models import ChangeKind, parse_diff


def test_demo_repository_contains_every_change_kind() -> None:
    """Build a self-contained mixed diff for demos and visual tests."""
    with create_demo_repository() as demo:
        files = parse_diff(text=demo.diff, project_root=demo.root).files

    assert [file.kind for file in files] == [
        ChangeKind.MODIFIED,
        ChangeKind.ADDED,
        ChangeKind.DELETED,
        ChangeKind.RENAMED,
        ChangeKind.RENAMED,
        ChangeKind.MODIFIED,
        ChangeKind.BINARY,
        ChangeKind.MODIFIED,
    ]
    assert [file.path for file in files] == [
        "src/calculator.py",
        "docs/guide.md",
        "legacy/old_config.py",
        "assets/new_name.txt",
        "src/new_module.py",
        "src/deeply/nested/subfolder/very_long_file_name_with_detailed_logic.py",
        "assets/logo.bin",
        "notes/no_newline.txt",
    ]
