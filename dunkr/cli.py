"""Command-line input and terminal handling for dunkr."""

import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, TextIO

from dunkr.models import DiffParseError


class InputError(RuntimeError):
    """Report input that cannot be obtained or parsed."""


def _terminal_error(error: OSError) -> InputError:
    """Build a concise boundary error for controlling-terminal failures."""
    return InputError(f"unable to access controlling terminal: {error}")


def _run_git(arguments: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run Git with stable text decoding and normalize launch failures."""
    try:
        return subprocess.run(
            ["git", *arguments],
            cwd=cwd,
            check=False,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as error:
        raise InputError(f"unable to run Git: {error}") from error


def read_diff(stdin: TextIO, cwd: Path) -> str:
    """Read a piped diff or obtain the working-tree diff from Git."""
    if not stdin.isatty():
        return stdin.read()
    completed = _run_git(arguments=["diff", "--no-color"], cwd=cwd)
    if completed.returncode:
        raise InputError(completed.stderr.strip() or "git diff failed")
    return completed.stdout


def resolve_project_root(cwd: Path) -> Path:
    """Return Git's repository root for repository-relative patch paths."""
    completed = _run_git(arguments=["rev-parse", "--show-toplevel"], cwd=cwd)
    if completed.returncode:
        raise InputError(
            completed.stderr.strip() or "unable to locate Git repository root"
        )
    root = completed.stdout.rstrip("\r\n")
    if not root:
        raise InputError("unable to locate Git repository root")
    return Path(root)


@contextmanager
def terminal_input(stdin: TextIO) -> Iterator[None]:
    """Reconnect file descriptor zero to the controlling terminal for Textual."""
    if stdin.isatty():
        yield
        return
    terminal_path = "CONIN$" if os.name == "nt" else "/dev/tty"
    try:
        stdin_fd = sys.__stdin__.fileno()
        saved_fd = os.dup(stdin_fd)
    except OSError as error:
        raise _terminal_error(error) from error
    try:
        try:
            terminal = open(terminal_path)
        except OSError as error:
            raise _terminal_error(error) from error
        try:
            try:
                os.dup2(terminal.fileno(), stdin_fd)
            except OSError as error:
                raise _terminal_error(error) from error
            yield
        finally:
            try:
                try:
                    os.dup2(saved_fd, stdin_fd)
                except OSError as error:
                    raise _terminal_error(error) from error
            finally:
                try:
                    terminal.close()
                except OSError as error:
                    raise _terminal_error(error) from error
    finally:
        try:
            os.close(saved_fd)
        except OSError as error:
            raise _terminal_error(error) from error


def main() -> int:
    """Resolve input, launch dunkr, and return a process exit status."""
    from dunkr.app import DunkrApp

    try:
        cwd = Path.cwd()
        stdin = sys.stdin
        diff = read_diff(stdin=stdin, cwd=cwd)
        project_root = resolve_project_root(cwd=cwd) if stdin.isatty() else cwd
        app = DunkrApp(diff=diff, project_root=project_root)
    except (DiffParseError, InputError) as error:
        print(f"dunkr: {error}", file=sys.stderr)
        return 1
    try:
        with terminal_input(sys.stdin):
            app.run()
    except InputError as error:
        print(f"dunkr: {error}", file=sys.stderr)
        return 1
    return 0
