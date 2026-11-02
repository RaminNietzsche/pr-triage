#!/usr/bin/env python3
"""Build a recall-eval KB: enrich a PR sample only (skip heavy base_patch index)."""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kb.build import build_snapshot  # noqa: E402
from kb.enrich import enrich_prs  # noqa: E402
from triage.gitdata import Git, base_ref  # noqa: E402
from pr_triage.safepath import resolve_under  # noqa: E402
from run import LIMITATIONS  # noqa: E402


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", default="data/recall-sample.json")
    ap.add_argument("--out", default="data/kb-snapshot-recall")
    ap.add_argument("--clone", default="data/repo/ceph")
    ap.add_argument("--raw", default="data/raw")
    args = ap.parse_args()

    nums = json.loads(resolve_under(args.sample, ROOT).read_text())["prs"]
    raw = resolve_under(args.raw, ROOT)
    clone = args.clone
    t0 = time.perf_counter()
    enriched = enrich_prs(raw, clone, numbers=nums)
    enrich_s = time.perf_counter() - t0
    n_ok = sum(1 for r in enriched if r.get("enriched"))

    git = Git(clone)
    tips = {}
    for base in sorted({r["base"] for r in enriched if r.get("enriched")}):
        ref = base_ref(base)
        if git.has_ref(ref):
            tips[base] = git.out("rev-parse", "--short", ref).strip()

    out = resolve_under(args.out, ROOT)
    manifest = build_snapshot(
        out,
        raw_dir=raw,
        enriched_records=enriched,
        limitations=LIMITATIONS,
        base_tips=tips,
    )
    manifest["n_enriched_subset"] = n_ok
    manifest["recall_sample_n"] = len(nums)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))

    stats = {
        "enrich_s": round(enrich_s, 1),
        "n_sample": len(nums),
        "n_enriched_ok": n_ok,
        "base_tips": tips,
    }
    (out / "build-stats.json").write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
