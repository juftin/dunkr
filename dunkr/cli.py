"""Command-line input and terminal handling for dunkr."""

import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, TextIO


class InputError(RuntimeError):
    """Report input that cannot be obtained or parsed."""


def read_diff(stdin: TextIO, cwd: Path) -> str:
    """Read a piped diff or obtain the working-tree diff from Git."""
    if not stdin.isatty():
        return stdin.read()
    completed = subprocess.run(
        ["git", "diff", "--no-color"],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        raise InputError(completed.stderr.strip() or "git diff failed")
    return completed.stdout


@contextmanager
def terminal_input(stdin: TextIO) -> Iterator[None]:
    """Reconnect file descriptor zero to the controlling terminal for Textual."""
    if stdin.isatty():
        yield
        return
    terminal_path = "CONIN$" if os.name == "nt" else "/dev/tty"
    stdin_fd = sys.__stdin__.fileno()
    saved_fd = os.dup(stdin_fd)
    try:
        with open(terminal_path) as terminal:
            os.dup2(terminal.fileno(), stdin_fd)
            yield
    finally:
        os.dup2(saved_fd, stdin_fd)
        os.close(saved_fd)


def main() -> int:
    """Resolve input, launch dunkr, and return a process exit status."""
    from dunkr.app import DunkrApp

    try:
        diff = read_diff(stdin=sys.stdin, cwd=Path.cwd())
    except InputError as error:
        print(f"dunkr: {error}", file=sys.stderr)
        return 1
    with terminal_input(sys.stdin):
        DunkrApp(diff=diff, project_root=Path.cwd()).run()
    return 0
