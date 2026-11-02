#!/usr/bin/env python3
"""Nightly-scale KB build: enrich all open PRs, index base branches, pack snapshot."""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kb.build import build_snapshot, pack_snapshot  # noqa: E402
from kb.enrich import enrich_prs  # noqa: E402
from kb.indexes import build_base_branch_patch_index  # noqa: E402
from triage.gitdata import Git  # noqa: E402
from triage.github_api import list_open_pulls  # noqa: E402

from pr_triage.safepath import SafePath, resolve_under  # noqa: E402
from run import LIMITATIONS  # noqa: E402


def dir_size_bytes(path: Path) -> int:
    total = 0
    for p in Path(path).rglob("*"):
        if p.is_file():
            total += p.stat().st_size
    return total


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/kb-snapshot-full")
    ap.add_argument("--clone", default="data/repo/ceph")
    ap.add_argument("--refresh-list", action="store_true", help="re-fetch GitHub list (needs GITHUB_TOKEN if rate-limited)")
    args = ap.parse_args()

    t_wall = time.perf_counter()
    raw = ROOT / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    if args.refresh_list:
        prs = list_open_pulls("ceph/ceph", raw, max_age_s=0)
    elif not any(raw.glob("pulls_open_p*.json")):
        prs = list_open_pulls("ceph/ceph", raw, max_age_s=0)
    else:
        from triage.collect import load_list

        prs = load_list(raw)
    print(f"Open PRs in cache: {len(prs)}")

    clone = resolve_under(args.clone, ROOT)
    if not clone.is_dir():
        sys.exit(f"Missing clone at {clone}; run scripts/setup_clone.sh first")

    t0 = time.perf_counter()
    enriched = enrich_prs(raw, str(clone), numbers=None)
    enrich_s = time.perf_counter() - t0
    n_ok = sum(1 for r in enriched if r.get("enriched"))
    print(f"Enriched {n_ok}/{len(enriched)} PRs in {enrich_s:.1f}s")

    out_dir = SafePath(args.out, ROOT)
    git = Git(str(clone))
    bases = sorted({r["base"] for r in enriched})
    tips, base_patch = build_base_branch_patch_index(git, bases)

    t0 = time.perf_counter()
    manifest = build_snapshot(
        out_dir,
        raw_dir=raw,
        enriched_records=enriched,
        limitations=LIMITATIONS,
        base_tips=tips,
    )
    manifest["indexes"]["base_patch_id"] = len(base_patch)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    idx_dir = out_dir / "indexes"
    (idx_dir / "base_patch_id.json").write_text(json.dumps(base_patch))
    build_s = time.perf_counter() - t0

    archive = resolve_under("data/kb-snapshot-full.tar.gz", ROOT)
    t0 = time.perf_counter()
    pack_snapshot(out_dir, archive)
    pack_s = time.perf_counter() - t0

    stats = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "wall_clock_s": round(time.perf_counter() - t_wall, 1),
        "enrich_s": round(enrich_s, 1),
        "snapshot_build_s": round(build_s, 1),
        "pack_s": round(pack_s, 1),
        "n_open": manifest["n_open"],
        "n_enriched": manifest["n_enriched"],
        "indexes": manifest["indexes"],
        "base_tips": tips,
        "snapshot_dir_bytes": dir_size_bytes(out_dir),
        "tarball_bytes": archive.stat().st_size if archive.exists() else 0,
        "paths": {"dir": str(out_dir), "tarball": str(archive)},
    }
    (out_dir / "build-stats.json").write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
