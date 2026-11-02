"""Resolve user-influenced filesystem paths under an allowed base directory."""

from __future__ import annotations

import os
import tarfile
from pathlib import Path
from typing import Iterator


class SafePathError(ValueError):
    """Raised when a path would escape the allowed base directory."""


def allowed_base(base: str | Path | None = None) -> Path:
    """Workspace root used for path checks (current working directory by default)."""
    return Path(os.path.realpath(base or os.getcwd()))


def canonical_path_str(path: str | Path, base: str | Path | None = None) -> str:
    """Return a path string rebuilt from a trusted base (path-traversal sanitizer)."""
    trusted = os.path.realpath(str(allowed_base(base)))
    parts = Path(path).parts
    if ".." in parts:
        raise SafePathError(f"path {path!r} contains parent traversal")
    raw = str(path)
    if os.path.isabs(raw):
        resolved = os.path.realpath(raw)
    else:
        resolved = os.path.realpath(os.path.join(trusted, *parts))
    if resolved != trusted and not resolved.startswith(trusted + os.sep):
        raise SafePathError(f"path {path!r} escapes allowed base {trusted}")
    rel = os.path.relpath(resolved, trusted)
    if rel == os.curdir:
        canonical = trusted
    else:
        canonical = os.path.realpath(os.path.join(trusted, rel))
    if canonical != trusted and not canonical.startswith(trusted + os.sep):
        raise SafePathError(f"path {path!r} escapes allowed base {trusted}")
    return canonical


def resolve_under(path: str | Path, base: str | Path | None = None) -> Path:
    """Resolve *path* under *base*; return a canonical path under the trusted base."""
    return Path(canonical_path_str(path, base))


def resolve_config_path(path: str | Path, *, workspace: str | Path | None = None) -> Path:
    """Config file paths must stay under the workspace (CWD)."""
    return resolve_under(path, workspace)


def assert_realpath_under(path: str | Path, base: str | Path | None = None) -> str:
    """Alias for :func:`canonical_path_str` (explicit real path for I/O sinks)."""
    return canonical_path_str(path, base)


class SafePath:
    """Path confined to a validated directory; I/O re-checks containment."""

    __slots__ = ("_base", "_path")

    def __init__(self, path: str | Path | SafePath, base: str | Path | None = None):
        self._base = allowed_base(base)
        if isinstance(path, SafePath):
            if base is not None:
                self._base = allowed_base(base)
            raw = path._path
        else:
            raw = path
        self._path = Path(canonical_path_str(raw, self._base))

    def __fspath__(self) -> str:
        return self._checked_str()

    def _checked_str(self) -> str:
        canonical = canonical_path_str(self._path, self._base)
        self._path = Path(canonical)
        return canonical

    def _checked(self) -> Path:
        return Path(self._checked_str())

    @property
    def path(self) -> Path:
        return self._checked()

    def __truediv__(self, name: str) -> SafePath:
        if not isinstance(name, str) or name in (".", "..") or "/" in name or "\\" in name:
            raise SafePathError(f"invalid path segment: {name!r}")
        combined = Path(self._checked_str()) / name
        return SafePath(combined, self._base)

    def mkdir(self, *, parents: bool = False, exist_ok: bool = False) -> None:
        self._checked().mkdir(parents=parents, exist_ok=exist_ok)

    def exists(self) -> bool:
        return self._checked().exists()

    def is_dir(self) -> bool:
        return self._checked().is_dir()

    def is_file(self) -> bool:
        return self._checked().is_file()

    def read_text(self, encoding: str | None = None, errors: str | None = None) -> str:
        return self._checked().read_text(encoding=encoding, errors=errors)

    def write_text(
        self,
        data: str,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> int:
        return self._checked().write_text(
            data, encoding=encoding, errors=errors, newline=newline
        )

    def open(self, mode: str = "r", **kwargs: object):
        return self._checked().open(mode, **kwargs)

    def glob(self, pattern: str) -> Iterator[SafePath]:
        if pattern.startswith("/") or ".." in Path(pattern).parts:
            raise SafePathError(f"invalid glob pattern: {pattern!r}")
        for hit in self._checked().glob(pattern):
            yield SafePath(hit, self._base)

    def stat(self):
        return self._checked().stat()

    def __str__(self) -> str:
        return self._checked_str()


def extract_tarball(tf: tarfile.TarFile, dest_dir: Path) -> None:
    """Extract *tf* into *dest_dir*, rejecting members that escape the target."""
    dest = Path(os.path.realpath(str(dest_dir)))
    dest.mkdir(parents=True, exist_ok=True)
    data_filter = getattr(tarfile, "data_filter", None)
    for member in tf.getmembers():
        name = member.name
        if name.startswith(("/", "\\")) or ".." in Path(name).parts:
            raise SafePathError(f"unsafe tar member: {name}")
        target = Path(os.path.realpath(dest / name))
        try:
            target.relative_to(dest)
        except ValueError as exc:
            raise SafePathError(f"tar member escapes target: {name}") from exc
        if data_filter is not None:
            member = data_filter(member, dest)
        tf.extract(member, dest)
