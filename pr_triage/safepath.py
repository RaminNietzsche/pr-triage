"""Resolve user-influenced filesystem paths under an allowed base directory."""

from __future__ import annotations

import os
import tarfile
from pathlib import Path


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
    tf.extractall(dest, filter="data")
