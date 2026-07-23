"""Deterministic mixed Git diffs for demos and visual regression tests."""

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from typing import Iterator

from dunkr.app import DunkrApp


@dataclass(frozen=True)
class DemoRepository:
    """A temporary repository and the mixed working-tree diff it contains."""

    root: Path
    """Repository root used to resolve changed-file paths."""

    diff: str
    """Deterministic unified diff spanning every demo change kind."""


def _git(root: Path, *args: str) -> str:
    """Run Git in ``root`` and return its text output."""
    return subprocess.run(
        ["git", *args],
        check=True,
        cwd=root,
        capture_output=True,
        text=True,
    ).stdout


def _write(root: Path, relative_path: str, content: str | bytes) -> None:
    """Write fixture content, creating its parent directories when needed."""
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content)


@contextmanager
def create_demo_repository() -> Iterator[DemoRepository]:
    """Yield a temporary Git repository with a stable mixed diff."""
    with TemporaryDirectory(prefix="dunkr-demo-") as temporary_directory:
        root = Path(temporary_directory)
        _git(root, "init", "--quiet")
        _git(root, "config", "user.name", "dunkr demo")
        _git(root, "config", "user.email", "demo@example.invalid")
        _write(
            root,
            "src/calculator.py",
            "def add(left: int, right: int) -> int:\n    return left + right\n",
        )
        _write(root, "legacy/old_config.py", "DEBUG = False\n")
        _write(root, "assets/old_name.txt", "A stable asset name.\n")
        _write(
            root, "src/old_module.py", "def greeting() -> str:\n    return 'hello'\n"
        )
        _write(root, "assets/logo.bin", b"\x00\x01original\xff")
        _write(root, "notes/no_newline.txt", "before")
        _git(root, "add", ".")
        _git(root, "commit", "--quiet", "-m", "Base demo tree")

        _write(
            root,
            "src/calculator.py",
            "def add(left: int, right: int) -> int:\n    return left + right + 1\n",
        )
        _write(root, "docs/guide.md", "# Guide\n\nUse the calculator carefully.\n")
        _git(root, "add", "docs/guide.md")
        (root / "legacy/old_config.py").unlink()
        _git(root, "mv", "assets/old_name.txt", "assets/new_name.txt")
        _git(root, "mv", "src/old_module.py", "src/new_module.py")
        _write(
            root,
            "src/new_module.py",
            "def greeting() -> str:\n    return 'hello, dunkr'\n",
        )
        _write(root, "assets/logo.bin", b"\x00\x01changed\xfe")
        _write(root, "notes/no_newline.txt", "after")

        path_groups = (
            ("src/calculator.py",),
            ("docs/guide.md",),
            ("legacy/old_config.py",),
            ("assets/old_name.txt", "assets/new_name.txt"),
            ("src/old_module.py", "src/new_module.py"),
            ("assets/logo.bin",),
            ("notes/no_newline.txt",),
        )
        diff = "".join(
            _git(root, "diff", "--no-color", "--find-renames=20%", "HEAD", "--", *paths)
            for paths in path_groups
        )
        yield DemoRepository(root=root, diff=diff)


def main() -> int:
    """Launch dunkr with the deterministic mixed-diff fixture."""
    with create_demo_repository() as demo:
        DunkrApp(diff=demo.diff, project_root=demo.root).run()
    return 0
