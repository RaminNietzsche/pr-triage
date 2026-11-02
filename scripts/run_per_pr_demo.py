#!/usr/bin/env python3
"""Demo per-PR pipeline on recent open PRs; write latency CSV and sample comments."""

import csv
import json
import shutil
import statistics
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kb.build import build_snapshot, pack_snapshot  # noqa: E402
from kb.enrich import enrich_prs  # noqa: E402
from kb.load import load_snapshot  # noqa: E402
from pipeline.comment import render_comment  # noqa: E402
from pipeline.filter import filter_findings  # noqa: E402
from pipeline.query import query_pr  # noqa: E402
from triage import dupes  # noqa: E402
from triage.github_api import list_open_pulls  # noqa: E402


def pick_recent(raw_dir: Path, n=20):
    prs = []
    for f in sorted(raw_dir.glob("pulls_open_p*.json")):
        prs.extend(json.loads(f.read_text()))
    prs.sort(key=lambda p: p["updated_at"], reverse=True)
    return [p["number"] for p in prs[:n]]


def simulate_download(tarball: Path, dest: Path) -> float:
    t0 = time.perf_counter()
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(tarball, dest)
    return time.perf_counter() - t0


def load_kb_timed(path: Path):
    t0 = time.perf_counter()
    snap = load_snapshot(path)
    return snap, time.perf_counter() - t0


def query_timed(snap, pr_number: int):
    t0 = time.perf_counter()
    findings, meta = query_pr(snap, pr_number, no_tracker=True)
    return findings, meta, time.perf_counter() - t0


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="demo output directory")
    ap.add_argument("--count", type=int, default=20)
    ap.add_argument("--skip-enrich", action="store_true")
    ap.add_argument("--kb", help="existing KB snapshot dir (skip local build)")
    ap.add_argument(
        "--tarball",
        help="cold tarball path for simulated download (default: data/kb-snapshot-full.tar.gz)",
    )
    ap.add_argument("--build-stats", help="build-stats.json from full KB build")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    raw = ROOT / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    list_open_pulls("ceph/ceph", raw, max_age_s=3600)
    numbers = pick_recent(raw, args.count)

    download_s = 0.0
    load_s = 0.0
    snap_dir = Path(args.kb) if args.kb else ROOT / "data" / "kb-snapshot"

    if args.kb:
        tarball = Path(args.tarball or ROOT / "data" / "kb-snapshot-full.tar.gz")
        if tarball.is_file():
            with tempfile.TemporaryDirectory(prefix="kb-dl-") as td:
                dest = Path(td) / tarball.name
                download_s = simulate_download(tarball, dest)
                snap, load_s = load_kb_timed(dest)
        else:
            snap, load_s = load_kb_timed(snap_dir)
    else:
        enriched = []
        if not args.skip_enrich:
            clone = ROOT / "data" / "repo" / "ceph"
            if clone.is_dir():
                print(f"Enriching {len(numbers)} PRs via git...")
                enriched = enrich_prs(raw, str(clone), numbers)
            else:
                print("No clone; KB will be metadata-only", file=sys.stderr)
        build_snapshot(snap_dir, raw_dir=raw, enriched_records=enriched)
        pack_snapshot(snap_dir, ROOT / "data" / "kb-snapshot.tar.gz")
        snap, load_s = load_kb_timed(snap_dir)

    by_n = {r["number"]: r for r in snap["records"]}
    rows = []
    all_cats = Counter()
    samples = []
    cold_all = []
    warm_all = []
    e2e_all = []

    dupes._MODEL = None
    for i, n in enumerate(numbers):
        if i == 0:
            findings, meta, cold_s = query_timed(snap, n)
            _, _, warm_s = query_timed(snap, n)
        else:
            cold_s = 0.0
            findings, meta, warm_s = query_timed(snap, n)
        e2e_s = download_s + load_s + (cold_s if i == 0 else warm_s)
        shown = filter_findings(findings)
        for f in shown:
            all_cats[f["category"]] += 1
        cold_all.append(cold_s)
        warm_all.append(warm_s)
        e2e_all.append(e2e_s)
        rows.append(
            {
                "pr": n,
                "download_s": round(download_s, 3),
                "load_s": round(load_s, 3),
                "query_cold_s": round(cold_s, 3),
                "query_warm_s": round(warm_s, 3),
                "e2e_cold_s": round(e2e_s, 3),
                "enriched": meta["enriched"],
                "candidates": meta["n_candidates"],
                "findings_total": len(findings),
                "findings_shown": len(shown),
            }
        )
        if len(samples) < 6 and shown:
            samples.append(
                {
                    "pr": n,
                    "categories": sorted({f["category"] for f in shown}),
                    "body": render_comment(
                        n, shown, by_n, snapshot_at=meta.get("snapshot_at") or "", latency_s=cold_s
                    ),
                }
            )

    def pct(vals, p):
        if not vals:
            return 0
        s = sorted(vals)
        return s[min(int(len(s) * p), len(s) - 1)]

    first_cold = cold_all[0] if cold_all else 0.0
    warm_only = warm_all[1:] if len(warm_all) > 1 else warm_all

    build_stats = {}
    if args.build_stats and Path(args.build_stats).is_file():
        build_stats = json.loads(Path(args.build_stats).read_text())

    manifest = snap.get("manifest", {})
    summary = {
        "n_prs": len(rows),
        "download_s": round(download_s, 3),
        "load_s": round(load_s, 3),
        "query_cold_first_s": round(first_cold, 3),
        "query_warm_first_s": round(warm_all[0], 3) if warm_all else 0,
        "p50_query_warm_s": round(pct(warm_only or warm_all, 0.5), 3),
        "p95_query_warm_s": round(pct(warm_only or warm_all, 0.95), 3),
        "max_query_warm_s": round(max(warm_all) if warm_all else 0, 3),
        "p50_e2e_warm_s": round(pct([download_s + load_s + w for w in (warm_only or warm_all)], 0.5), 3),
        "p95_e2e_warm_s": round(pct([download_s + load_s + w for w in (warm_only or warm_all)], 0.95), 3),
        "max_e2e_warm_s": round(max(download_s + load_s + w for w in warm_all) if warm_all else 0, 3),
        "e2e_cold_first_s": round(e2e_all[0], 3) if e2e_all else 0,
        "category_hits": dict(all_cats),
        "snapshot": str(snap_dir),
        "manifest": {
            "n_open": manifest.get("n_open"),
            "n_enriched": manifest.get("n_enriched"),
            "indexes": manifest.get("indexes"),
            "base_tips": manifest.get("base_tips"),
        },
        "build": build_stats,
    }
    if build_stats:
        summary["snapshot_mb"] = {
            "dir": round(build_stats.get("snapshot_dir_bytes", 0) / 1e6, 2),
            "tarball": round(build_stats.get("tarball_bytes", 0) / 1e6, 2),
        }

    fields = [
        "pr",
        "download_s",
        "load_s",
        "query_cold_s",
        "query_warm_s",
        "e2e_cold_s",
        "enriched",
        "candidates",
        "findings_total",
        "findings_shown",
    ]
    with open(out / "latency.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    md = ["# Per-PR demo sample comments", "", f"Generated {datetime.now(timezone.utc).isoformat()}", ""]
    picked = []
    seen_cats = set()
    for s in samples:
        cat = s["categories"][0] if s["categories"] else "other"
        if cat in seen_cats and len(picked) >= 3:
            continue
        seen_cats.add(cat)
        picked.append(s)
        if len(picked) >= 3:
            break
    for s in picked[:3]:
        md += [f"## PR #{s['pr']}", "", s["body"], ""]
    (out / "sample-comments.md").write_text("\n".join(md))
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
