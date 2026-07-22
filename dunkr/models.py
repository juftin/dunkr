"""Application-owned models for parsed unified diffs."""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath

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
    source_display_path: str | None
    target_display_path: str | None
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


def _decode_git_path(path: str) -> str:
    """Decode a valid Git C-quoted path, including octal UTF-8 bytes."""
    if not path.startswith('"'):
        return path
    if not path.endswith('"'):
        raise DiffParseError(f"invalid quoted patch path: {path}")
    value = path[1:-1]
    decoded = bytearray()
    escapes = {
        "a": b"\a",
        "b": b"\b",
        "t": b"\t",
        "n": b"\n",
        "v": b"\v",
        "f": b"\f",
        "r": b"\r",
        "\\": b"\\",
        '"': b'"',
    }
    index = 0
    while index < len(value):
        character = value[index]
        if character != "\\":
            decoded.extend(character.encode("utf-8"))
            index += 1
            continue
        index += 1
        if index == len(value):
            raise DiffParseError(f"invalid quoted patch path: {path}")
        escape = value[index]
        if escape in "01234567":
            end = index + 1
            while end < min(index + 3, len(value)) and value[end] in "01234567":
                end += 1
            decoded.append(int(value[index:end], 8))
            index = end
            continue
        if escape not in escapes:
            raise DiffParseError(f"invalid quoted patch path: {path}")
        decoded.extend(escapes[escape])
        index += 1
    try:
        result = decoded.decode("utf-8")
    except UnicodeDecodeError as error:
        raise DiffParseError(f"invalid quoted patch path: {path}") from error
    if "\0" in result:
        raise DiffParseError(f"invalid quoted patch path: {path}")
    return result


def _repository_path(path: str, prefix: str) -> str | None:
    """Decode and validate one repository-relative patch path."""
    decoded_path = _decode_git_path(path)
    if decoded_path == "/dev/null":
        return None
    repository_path = decoded_path.removeprefix(prefix)
    relative_path = PurePosixPath(repository_path)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise DiffParseError(f"unsafe patch path: {decoded_path}")
    return str(relative_path)


def _project_path(repository_path: str | None, project_root: Path) -> Path | None:
    """Map a validated repository path to its location under ``project_root``."""
    if repository_path is None:
        return None
    return project_root.joinpath(*PurePosixPath(repository_path).parts)


def parse_diff(text: str, project_root: Path) -> DiffSet:
    """Parse unified text into file models rooted at ``project_root``."""
    if not text.strip():
        return DiffSet(files=())
    try:
        patches = PatchSet(text)
    except (AttributeError, UnidiffParseError, UnboundLocalError, ValueError) as error:
        raise DiffParseError(str(error)) from error
    if not patches:
        raise DiffParseError("input contains no parsed patches")
    files: list[DiffFile] = []
    for patch in patches:
        source_display_path = _repository_path(path=patch.source_file, prefix="a/")
        target_display_path = _repository_path(path=patch.target_file, prefix="b/")
        files.append(
            DiffFile(
                path=target_display_path or source_display_path or patch.path,
                source_display_path=source_display_path,
                target_display_path=target_display_path,
                source_path=_project_path(
                    repository_path=source_display_path, project_root=project_root
                ),
                target_path=_project_path(
                    repository_path=target_display_path, project_root=project_root
                ),
                kind=_change_kind(patch),
                additions=patch.added,
                deletions=patch.removed,
                is_binary=patch.is_binary_file,
                patch=patch,
            )
        )
    return DiffSet(files=tuple(files))
