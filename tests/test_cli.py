"""Tests for dunkr's command-line boundary."""

import io
import subprocess
import sys
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Iterator, TextIO

import pytest

import dunkr.cli as cli
from dunkr.app import DunkrApp
from dunkr.cli import InputError, main, read_diff
from tests.test_models import MODIFIED_DIFF


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


def test_read_diff_replaces_non_utf8_git_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Decode implicit Git output without crashing on invalid UTF-8 bytes."""
    stdin = FakeStdin(is_terminal=True)

    def completed_run(
        *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        """Return output decoded according to the subprocess error policy."""
        encoding = kwargs.get("encoding")
        errors = kwargs.get("errors")
        assert encoding == "utf-8"
        assert errors == "replace"
        return subprocess.CompletedProcess(
            args=["git", "diff", "--no-color"],
            returncode=0,
            stdout=b"before:\xff:after".decode(encoding, errors=errors),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", completed_run)

    assert read_diff(stdin=stdin, cwd=Path("/repo")) == "before:\ufffd:after"


def test_read_diff_reports_git_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Convert a failed implicit Git invocation into a CLI error."""
    stdin = FakeStdin(is_terminal=True)
    completed = subprocess.CompletedProcess(
        args=["git", "diff", "--no-color"],
        returncode=128,
        stdout="",
        stderr="not a repo",
    )
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: completed)

    with pytest.raises(InputError, match="not a repo"):
        read_diff(stdin=stdin, cwd=Path("/repo"))


def test_read_diff_reports_git_launch_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Convert an operating-system Git launch failure into a CLI error."""
    stdin = FakeStdin(is_terminal=True)

    def failed_run(*args: object, **kwargs: object) -> None:
        """Simulate Git being unavailable to the process."""
        raise OSError("git executable unavailable")

    monkeypatch.setattr(subprocess, "run", failed_run)

    with pytest.raises(InputError, match="git executable unavailable"):
        read_diff(stdin=stdin, cwd=Path("/repo"))


def test_main_reports_git_launch_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Return nonzero with a concise error when Git cannot be launched."""

    def failed_run(*args: object, **kwargs: object) -> None:
        """Simulate Git being unavailable to the process."""
        raise OSError("git executable unavailable")

    monkeypatch.setattr(sys, "stdin", FakeStdin(is_terminal=True))
    monkeypatch.setattr(subprocess, "run", failed_run)

    assert main() == 1
    assert capsys.readouterr().err == (
        "dunkr: unable to run Git: git executable unavailable\n"
    )


def test_main_maps_paths_from_git_root_when_invoked_in_nested_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Root parsed repository paths at Git's top level from a nested cwd."""
    repository = tmp_path / "repository"
    nested = repository / "src" / "package"
    nested.mkdir(parents=True)
    launched: list[DunkrApp] = []

    def completed_run(
        *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        """Return the repository root for Git's top-level query."""
        assert args[0] == ["git", "rev-parse", "--show-toplevel"]
        assert kwargs["cwd"] == nested
        return subprocess.CompletedProcess(
            args=args[0], returncode=0, stdout=f"{repository}\n", stderr=""
        )

    def record_run(app: DunkrApp) -> None:
        """Capture the initialized application without launching Textual."""
        launched.append(app)

    monkeypatch.chdir(nested)
    monkeypatch.setattr(sys, "stdin", FakeStdin(MODIFIED_DIFF))
    monkeypatch.setattr(subprocess, "run", completed_run)
    monkeypatch.setattr(cli, "terminal_input", lambda stdin: nullcontext())
    monkeypatch.setattr(DunkrApp, "run", record_run)

    assert main() == 0
    assert launched[0].diff_set.files[0].target_path == repository / "example.py"


def test_terminal_input_reports_controlling_terminal_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Normalize a controlling-terminal open failure as an input error."""
    stdin = FakeStdin()

    class TerminalStdin:
        """Expose a stable descriptor for terminal handoff setup."""

        @staticmethod
        def fileno() -> int:
            """Return standard input's descriptor."""
            return 0

    def failed_open(*args: object, **kwargs: object) -> None:
        """Simulate an unavailable controlling terminal."""
        raise OSError("no controlling terminal")

    monkeypatch.setattr(cli.sys, "__stdin__", TerminalStdin())
    monkeypatch.setattr(cli.os, "dup", lambda descriptor: 99)
    monkeypatch.setattr(cli.os, "dup2", lambda source, target: None)
    monkeypatch.setattr(cli.os, "close", lambda descriptor: None)
    monkeypatch.setattr("builtins.open", failed_open)

    with pytest.raises(InputError, match="no controlling terminal"):
        with cli.terminal_input(stdin=stdin):
            pass


def test_main_reports_controlling_terminal_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Return nonzero with a concise error when terminal handoff fails."""

    @contextmanager
    def failed_terminal_input(stdin: TextIO) -> Iterator[None]:
        """Simulate terminal handoff already normalized by the boundary."""
        raise InputError("unable to access controlling terminal: unavailable")
        yield

    monkeypatch.setattr(sys, "stdin", FakeStdin(""))
    monkeypatch.setattr(cli, "resolve_project_root", lambda cwd: cwd)
    monkeypatch.setattr(cli, "terminal_input", failed_terminal_input)

    assert main() == 1
    assert capsys.readouterr().err == (
        "dunkr: unable to access controlling terminal: unavailable\n"
    )


def test_main_reports_a_malformed_piped_diff(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exit concisely when piped input is not a unified diff."""
    monkeypatch.setattr(sys, "stdin", FakeStdin("not a diff"))
    monkeypatch.setattr(cli, "resolve_project_root", lambda cwd: cwd)

    assert main() == 1
    assert capsys.readouterr().err == ("dunkr: input contains no parsed patches\n")
