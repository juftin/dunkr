"""Application-owned models for parsed unified diffs."""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from unidiff import PatchSet
from unidiff.errors import UnidiffParseError
from unidiff.patch import PatchedFile


class DiffParseError(ValueError):
    """Report malformed unified diff input."""


class ChangeKind(Enum):
    """Describe a file-level Git change."""

    MODIFIED = "modified"
    ADDED = "added"
    DELETED = "deleted"
    RENAMED = "renamed"
    BINARY = "binary"


@dataclass(frozen=True)
class DiffFile:
    """Stable file metadata plus parser state needed by native rendering."""

    path: str
    source_path: Path | None
    target_path: Path | None
    kind: ChangeKind
    additions: int
    deletions: int
    is_binary: bool
    patch: PatchedFile


@dataclass(frozen=True)
class DiffSet:
    """An ordered collection of changed files."""

    files: tuple[DiffFile, ...]


def _change_kind(patch: PatchedFile) -> ChangeKind:
    """Map unidiff flags to one stable application change kind."""
    if patch.is_binary_file:
        return ChangeKind.BINARY
    if patch.is_added_file:
        return ChangeKind.ADDED
    if patch.is_removed_file:
        return ChangeKind.DELETED
    if patch.is_rename:
        return ChangeKind.RENAMED
    return ChangeKind.MODIFIED


def _project_path(path: str, prefix: str, project_root: Path) -> Path | None:
    """Return a project path, preserving ``/dev/null`` as an absent-side sentinel."""
    if path == "/dev/null":
        return None
    relative_path = Path(path.removeprefix(prefix))
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise DiffParseError(f"unsafe patch path: {path}")
    return project_root / relative_path


def parse_diff(text: str, project_root: Path) -> DiffSet:
    """Parse unified text into file models rooted at ``project_root``."""
    if not text.strip():
        return DiffSet(files=())
    try:
        patches = PatchSet(text)
    except (UnidiffParseError, UnboundLocalError, ValueError) as error:
        raise DiffParseError(str(error)) from error
    if not patches:
        raise DiffParseError("input contains no parsed patches")
    files = tuple(
        DiffFile(
            path=patch.path,
            source_path=_project_path(
                path=patch.source_file, prefix="a/", project_root=project_root
            ),
            target_path=_project_path(
                path=patch.target_file, prefix="b/", project_root=project_root
            ),
            kind=_change_kind(patch),
            additions=patch.added,
            deletions=patch.removed,
            is_binary=patch.is_binary_file,
            patch=patch,
        )
        for patch in patches
    )
    return DiffSet(files=files)
