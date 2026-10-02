"""Capture and compare deterministic SVG screenshots of the dunkr demo."""

import argparse
import asyncio
import re
import subprocess
from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory

from dunkr.app import DunkrApp, FileSidebar
from dunkr.demo import create_demo_repository

SnapshotState = tuple[str, int | None, bool]
"""A named screenshot state with optional sidebar navigation or hiding."""

SNAPSHOT_STATES: tuple[SnapshotState, ...] = (
    ("all-files-overview", None, False),
    ("rename-section", 3, False),
    ("binary-section", 6, False),
    ("sidebar-hidden", None, True),
)
"""The committed visual states for the mixed-diff demo."""

_TITLE_PATTERN = re.compile(r"<title>.*?</title>", flags=re.DOTALL)
_TIMESTAMP_PATTERN = re.compile(r'\s(?:timestamp|data-timestamp)="[^"]*"')


def normalize_svg(svg: str) -> str:
    """Remove volatile metadata and normalize rect line height to prevent subpixel gaps."""
    cleaned = _TIMESTAMP_PATTERN.sub(
        "", _TITLE_PATTERN.sub("<title>dunkr</title>", svg)
    )
    return cleaned.replace('height="24.65"', 'height="24.9"')


async def capture_demo_state(
    *,
    name: str,
    selection: int | None,
    sidebar_hidden: bool,
    size: tuple[int, int],
) -> str:
    """Capture one named visual state from the deterministic mixed-diff app."""
    with create_demo_repository() as demo:
        app = DunkrApp(diff=demo.diff, project_root=demo.root)
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            if selection is not None:
                app.query_one(FileSidebar).index = selection
                await pilot.pause()
            if sidebar_hidden:
                await pilot.press("b")
                await pilot.pause()
            return normalize_svg(app.export_screenshot(title=name, simplify=True))


async def capture_snapshots() -> dict[str, str]:
    """Capture every committed visual state at the fixed regression size."""
    captures: dict[str, str] = {}
    for name, selection, sidebar_hidden in SNAPSHOT_STATES:
        captures[name] = await capture_demo_state(
            name=name,
            selection=selection,
            sidebar_hidden=sidebar_hidden,
            size=(140, 42),
        )
    return captures


def _write_preview(*, name: str, svg: str) -> None:
    """Render an inspectable PNG preview without changing the SVG oracle."""
    preview_path = Path("artifacts/screenshots") / f"{name}.png"
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="dunkr-snapshot-") as temporary_directory:
        source_dir = Path(temporary_directory)
        source = source_dir / f"{name}.svg"
        source.write_text(svg)
        try:
            subprocess.run(
                [
                    "qlmanage",
                    "-t",
                    "-s",
                    "1726",
                    "-o",
                    str(source_dir),
                    str(source),
                ],
                check=True,
                capture_output=True,
            )
            rendered = source_dir / f"{name}.svg.png"
            if rendered.is_file():
                rendered.replace(preview_path)
                return
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass

        try:
            subprocess.run(
                [
                    "sips",
                    "-s",
                    "format",
                    "png",
                    str(source),
                    "--out",
                    str(preview_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as error:
            raise RuntimeError(
                "PNG previews require qlmanage or sips command."
            ) from error


def main(argv: Sequence[str] | None = None) -> int:
    """Compare demo captures to baselines or update them only when requested."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update", action="store_true")
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("tests/snapshots"))
    arguments = parser.parse_args(argv)
    captures = asyncio.run(capture_snapshots())

    mismatches: list[str] = []
    for name, svg in captures.items():
        baseline = arguments.output / f"{name}.svg"
        if arguments.update:
            baseline.parent.mkdir(parents=True, exist_ok=True)
            baseline.write_text(svg)
        elif not baseline.is_file() or baseline.read_text() != svg:
            mismatches.append(name)
        if arguments.preview:
            _write_preview(name=name, svg=svg)

    if mismatches:
        print(f"Visual baselines differ: {', '.join(mismatches)}")
        return 1
    return 0
