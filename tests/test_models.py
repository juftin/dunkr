"""Tests for application-owned diff models."""

from pathlib import Path

import pytest

from dunkr.models import ChangeKind, DiffParseError, parse_diff


MODIFIED_DIFF = """\
diff --git a/example.py b/example.py
index 0000000..1111111 100644
--- a/example.py
+++ b/example.py
@@ -1 +1 @@
-print("before")
+print("after")
"""


def test_parse_diff_exposes_file_metadata(tmp_path: Path) -> None:
    """Expose stable metadata without requiring widgets to inspect unidiff."""
    (tmp_path / "example.py").write_text('print("after")\n')

    diff_set = parse_diff(text=MODIFIED_DIFF, project_root=tmp_path)

    assert len(diff_set.files) == 1
    file = diff_set.files[0]
    assert file.path == "example.py"
    assert file.kind is ChangeKind.MODIFIED
    assert file.additions == 1
    assert file.deletions == 1
    assert file.target_path == tmp_path / "example.py"


def test_parse_diff_preserves_repository_b_path_component(tmp_path: Path) -> None:
    """Retain a real leading ``b`` directory after stripping diff prefixes."""
    text = "--- a/b/example.py\n+++ b/b/example.py\n@@ -1 +1 @@\n-old\n+new\n"

    file = parse_diff(text=text, project_root=tmp_path).files[0]

    assert file.source_path == tmp_path / "b/example.py"
    assert file.target_path == tmp_path / "b/example.py"


def test_parse_diff_accepts_empty_input(tmp_path: Path) -> None:
    """Represent an empty working tree without raising an error."""
    assert parse_diff(text="", project_root=tmp_path).files == ()


def test_parse_added_file(tmp_path: Path) -> None:
    """Classify a /dev/null source as an added file."""
    text = "--- /dev/null\n+++ b/new.py\n@@ -0,0 +1 @@\n+new = True\n"
    file = parse_diff(text=text, project_root=tmp_path).files[0]
    assert file.kind is ChangeKind.ADDED
    assert file.source_path is None
    assert file.target_path == tmp_path / "new.py"
    assert not file.is_binary


def test_parse_deleted_file(tmp_path: Path) -> None:
    """Classify a /dev/null target as a deleted file."""
    text = "--- a/old.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-old = True\n"
    file = parse_diff(text=text, project_root=tmp_path).files[0]
    assert file.kind is ChangeKind.DELETED
    assert file.source_path == tmp_path / "old.py"
    assert file.target_path is None
    assert not file.is_binary


def test_parse_renamed_file(tmp_path: Path) -> None:
    """Expose both paths for a pure rename."""
    text = (
        "diff --git a/pkg/old/name.py b/pkg/new/name.py\n"
        "similarity index 100%\n"
        "rename from pkg/old/name.py\n"
        "rename to pkg/new/name.py\n"
    )
    file = parse_diff(text=text, project_root=tmp_path).files[0]
    assert file.kind is ChangeKind.RENAMED
    assert file.source_path == tmp_path / "pkg/old/name.py"
    assert file.target_path == tmp_path / "pkg/new/name.py"


def test_parse_diff_decodes_git_c_quoted_utf8_path(tmp_path: Path) -> None:
    """Decode Git's octal UTF-8 and escaped special characters before mapping."""
    text = (
        'diff --git "a/docs/caf\\303\\251\\t\\"quoted\\".py" '
        '"b/docs/caf\\303\\251\\t\\"quoted\\".py"\n'
        '--- "a/docs/caf\\303\\251\\t\\"quoted\\".py"\n'
        '+++ "b/docs/caf\\303\\251\\t\\"quoted\\".py"\n'
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )
    repository_path = 'docs/café\t"quoted".py'

    file = parse_diff(text=text, project_root=tmp_path).files[0]

    assert file.path == repository_path
    assert file.source_path == tmp_path / repository_path
    assert file.target_path == tmp_path / repository_path


def test_parse_binary_file(tmp_path: Path) -> None:
    """Classify Git's binary marker without reading file content."""
    text = "diff --git a/image.png b/image.png\nBinary files a/image.png and b/image.png differ\n"
    file = parse_diff(text=text, project_root=tmp_path).files[0]
    assert file.kind is ChangeKind.BINARY
    assert file.is_binary


def test_parse_diff_normalizes_truncated_git_binary_patch(tmp_path: Path) -> None:
    """Convert unidiff's truncated binary marker failure into a parse error."""
    with pytest.raises(DiffParseError):
        parse_diff(text="GIT binary patch\n", project_root=tmp_path)


@pytest.mark.parametrize("text", ("+++ b/x\n", "not a diff"))
def test_parse_diff_rejects_malformed_or_patchless_input(
    text: str, tmp_path: Path
) -> None:
    """Raise an application error for nonempty input without parsed patches."""
    with pytest.raises(DiffParseError):
        parse_diff(text=text, project_root=tmp_path)


@pytest.mark.parametrize("path", ("../../outside.py", "/tmp/outside.py"))
def test_parse_diff_rejects_paths_outside_project_root(
    path: str, tmp_path: Path
) -> None:
    """Reject traversal and absolute paths supplied by a parsed patch."""
    text = f"--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n-old\n+new\n"

    with pytest.raises(DiffParseError):
        parse_diff(text=text, project_root=tmp_path)
