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


def resolve_under(path: str | Path, base: str | Path | None = None) -> Path:
    """Resolve *path* under *base*; reject traversal outside *base*."""
    root = allowed_base(base)
    p = Path(path)
    if ".." in p.parts:
        raise SafePathError(f"path {path!r} contains parent traversal")
    if p.is_absolute():
        resolved = Path(os.path.realpath(p))
    else:
        resolved = Path(os.path.realpath(root / p))
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise SafePathError(f"path {path!r} escapes allowed base {root}") from exc
    return resolved


def resolve_config_path(path: str | Path, *, workspace: str | Path | None = None) -> Path:
    """Config file paths must stay under the workspace (CWD)."""
    return resolve_under(path, workspace)


class SafePath:
    """Path confined to a validated directory; I/O re-checks containment."""

    __slots__ = ("_base", "_path")

    def __init__(self, path: str | Path | SafePath, base: str | Path | None = None):
        if isinstance(path, SafePath):
            self._base = allowed_base(base) if base is not None else path._base
            self._path = resolve_under(path._path, self._base)
            return
        self._base = allowed_base(base)
        self._path = resolve_under(path, self._base)

    def __fspath__(self) -> str:
        return str(self._checked())

    def _checked(self) -> Path:
        resolved = resolve_under(self._path, self._base)
        self._path = resolved
        return resolved

    @property
    def path(self) -> Path:
        return self._checked()

    def __truediv__(self, name: str) -> SafePath:
        if not isinstance(name, str) or name in (".", "..") or "/" in name or "\\" in name:
            raise SafePathError(f"invalid path segment: {name!r}")
        return SafePath(self._path / name, self._base)

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
        return self._checked().write_text(data, encoding=encoding, errors=errors, newline=newline)

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
        return str(self._path)


def extract_tarball(tf: tarfile.TarFile, dest_dir: Path) -> None:
    """Extract *tf* into *dest_dir*, rejecting members that escape the target."""
    dest = allowed_base(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    for member in tf.getmembers():
        name = member.name
        if name.startswith(("/", "\\")) or ".." in Path(name).parts:
            raise SafePathError(f"unsafe tar member: {name}")
        target = Path(os.path.realpath(dest / name))
        try:
            target.relative_to(dest)
        except ValueError as exc:
            raise SafePathError(f"tar member escapes target: {name}") from exc
    data_filter = getattr(tarfile, "data_filter", None)
    if data_filter is not None:
        tf.extractall(dest, filter=data_filter)
    else:
        tf.extractall(dest)
