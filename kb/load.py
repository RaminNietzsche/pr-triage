"""Load KB snapshot from directory or tarball."""

import json
import tarfile
from pathlib import Path

from pr_triage.safepath import SafePath, allowed_base, extract_tarball, resolve_under


def _read_json(path: Path):
    return json.loads(SafePath(path, allowed_base()).read_text())


def load_snapshot(path: Path):
    """Return dict with manifest, records (list), indexes."""
    path = resolve_under(path, allowed_base())
    if path.suffixes[-2:] == [".tar", ".gz"] or path.name.endswith(".tar.gz"):
        return _load_tarball(path)
    return _load_dir(path)


def _load_dir(root: Path):
    base = allowed_base()
    manifest = _read_json(root / "manifest.json")
    records = []
    prs = root / "prs.jsonl"
    if prs.exists():
        for line in SafePath(prs, base).read_text().splitlines():
            if line.strip():
                records.append(json.loads(line))
    elif (root / "prs.json").exists():
        blob = _read_json(root / "prs.json")
        records = blob if isinstance(blob, list) else blob.get("all", [])
    idx_dir = root / "indexes"
    indexes = {}
    if idx_dir.is_dir():
        for f in idx_dir.glob("*.json"):
            indexes[f.stem.replace("_", "_")] = _read_json(f)
        # normalize keys file vs eff_patch
        indexes = {
            "patch_id": indexes.get("patch_id", {}),
            "eff_patch": indexes.get("eff_patch", {}),
            "file": indexes.get("file", {}),
            "ticket": indexes.get("ticket", {}),
            "base_patch_id": indexes.get("base_patch_id", {}),
        }
    return {"manifest": manifest, "records": records, "indexes": indexes, "root": root}


def _load_tarball(archive: Path):
    import tempfile

    with tempfile.TemporaryDirectory(prefix="kb-snap-") as td:
        dest = Path(td)
        with tarfile.open(archive, "r:gz") as tf:
            extract_tarball(tf, dest)
        root = dest
        subs = [p for p in root.iterdir() if p.is_dir()]
        snap = subs[0] if len(subs) == 1 else root
        return _load_dir(snap)
