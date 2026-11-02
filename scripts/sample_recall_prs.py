#!/usr/bin/env python3
"""Stratified sample of PRs with batch high-precision findings for recall eval."""

import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.agreement import load_batch_hp_rows, norm_category  # noqa: E402

# PRs that stress structural + duplicate categories in the tightened batch CSV
ANCHOR = {62462, 43518, 70017, 67875}


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--batch-csv", default="reports/all-2026-11-02.csv")
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    hp = load_batch_hp_rows(ROOT / args.batch_csv)
    by_cat = defaultdict(set)
    all_prs = set()
    for f in hp:
        cat = norm_category(f["category"])
        for n in f["prs"]:
            by_cat[cat].add(n)
            all_prs.add(n)

    rng = random.Random(args.seed)
    picked = set(ANCHOR)
    cats = sorted(by_cat.keys())
    per_cat = max(3, args.n // max(1, len(cats)))
    for cat in cats:
        pool = sorted(by_cat[cat] - picked)
        rng.shuffle(pool)
        picked.update(pool[:per_cat])

    for f in hp:
        if norm_category(f["category"]) in ("duplicate", "duplicate-backport", "stated-supersede"):
            if any(p in picked for p in f["prs"]):
                picked.update(f["prs"])

    remainder = sorted(all_prs - picked)
    rng.shuffle(remainder)
    for n in remainder:
        if len(picked) >= args.n:
            break
        picked.add(n)

    sample = sorted(picked)[: args.n]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "n_requested": args.n,
        "n_sampled": len(sample),
        "seed": args.seed,
        "anchor_prs": sorted(ANCHOR),
        "category_counts_in_batch": {c: len(by_cat[c]) for c in cats},
        "prs": sample,
    }
    out.write_text(json.dumps(payload, indent=2))
    print(json.dumps({"n": len(sample), "out": str(out)}, indent=2))


if __name__ == "__main__":
    main()
