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
    source_path: Path
    target_path: Path
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


def parse_diff(text: str, project_root: Path) -> DiffSet:
    """Parse unified text into file models rooted at ``project_root``."""
    if not text.strip():
        return DiffSet(files=())
    try:
        patches = PatchSet(text)
    except (UnidiffParseError, ValueError) as error:
        raise DiffParseError(str(error)) from error
    files = tuple(
        DiffFile(
            path=patch.path,
            source_path=project_root / patch.source_file.removeprefix("a/"),
            target_path=project_root / patch.target_file.removeprefix("b/"),
            kind=_change_kind(patch),
            additions=patch.added,
            deletions=patch.removed,
            is_binary=patch.is_binary_file,
            patch=patch,
        )
        for patch in patches
    )
    return DiffSet(files=files)
