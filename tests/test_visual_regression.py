"""Visual baseline tests for the deterministic dunkr demo."""

import asyncio
from pathlib import Path

import pytest

from dunkr.snapshots import main
from tests.visual import assert_snapshot, capture_demo_state


@pytest.mark.parametrize(
    ("name", "selection", "sidebar_hidden"),
    [
        ("all-files-overview", None, False),
        ("rename-section", 3, False),
        ("binary-section", 6, False),
        ("sidebar-hidden", None, True),
    ],
)
def test_visual_baseline(
    name: str, selection: int | None, sidebar_hidden: bool
) -> None:
    """Compare a deterministic Textual SVG state with its committed baseline."""
    svg = asyncio.run(
        capture_demo_state(
            name=name,
            selection=selection,
            sidebar_hidden=sidebar_hidden,
            size=(140, 42),
        )
    )
    assert_snapshot(name=name, svg=svg)


def test_snapshot_command_requires_update_to_write_baselines(tmp_path: Path) -> None:
    """Prevent ordinary snapshot runs from rewriting visual expectations."""
    assert main(argv=["--output", str(tmp_path)]) == 1
    assert main(argv=["--output", str(tmp_path), "--update"]) == 0
