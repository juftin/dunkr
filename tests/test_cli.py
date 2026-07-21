"""Tests for dunkr's command-line boundary."""

import io
import subprocess
from pathlib import Path
import pytest

from dunkr.cli import InputError, read_diff


class FakeStdin(io.StringIO):
    """Provide a controllable terminal status for command-line input tests."""

    def __init__(self, content: str = "", is_terminal: bool = False) -> None:
        """Initialize the stream with content and a terminal status."""
        super().__init__(content)
        self._is_terminal = is_terminal

    def isatty(self) -> bool:
        """Return the configured terminal status."""
        return self._is_terminal


def test_read_diff_uses_piped_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use explicit input without invoking Git."""
    stdin = FakeStdin("diff --git a/a.py b/a.py\n")

    def unexpected_run(*args: object, **kwargs: object) -> None:
        """Fail if piped input incorrectly invokes Git."""
        raise AssertionError("git must not run for piped input")

    monkeypatch.setattr(subprocess, "run", unexpected_run)
    assert read_diff(stdin=stdin, cwd=Path("/repo")) == stdin.getvalue()


def test_read_diff_runs_git_for_a_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Obtain the working-tree diff when no pipe is present."""
    stdin = FakeStdin(is_terminal=True)
    completed = subprocess.CompletedProcess(
        args=["git", "diff", "--no-color"], returncode=0, stdout="the diff", stderr=""
    )
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: completed)

    assert read_diff(stdin=stdin, cwd=Path("/repo")) == "the diff"


def test_read_diff_reports_git_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Convert a failed implicit Git invocation into a CLI error."""
    stdin = FakeStdin(is_terminal=True)
    completed = subprocess.CompletedProcess(
        args=["git", "diff", "--no-color"], returncode=128, stdout="", stderr="not a repo"
    )
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: completed)

    with pytest.raises(InputError, match="not a repo"):
        read_diff(stdin=stdin, cwd=Path("/repo"))
