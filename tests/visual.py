"""Shared assertions for dunkr SVG visual-regression tests."""

from pathlib import Path

from dunkr.snapshots import capture_demo_state, normalize_svg

__all__ = ["assert_snapshot", "capture_demo_state"]


SNAPSHOT_DIRECTORY = Path(__file__).parent / "snapshots"
"""Committed SVG visual-regression baselines."""


def assert_snapshot(*, name: str, svg: str) -> None:
    """Assert that a normalized SVG matches its named committed baseline."""
    baseline = SNAPSHOT_DIRECTORY / f"{name}.svg"
    assert baseline.is_file(), f"Missing visual baseline: {baseline}"
    assert baseline.read_text() == normalize_svg(svg)
