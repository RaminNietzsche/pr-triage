#!/usr/bin/env python3
"""Stratified sample of PRs with batch high-precision findings for recall eval."""

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.agreement import load_batch_hp_rows, norm_category  # noqa: E402
from pr_triage.safepath import SafePath  # noqa: E402

# PRs that stress structural + duplicate categories in the tightened batch CSV
ANCHOR = {62462, 43518, 70017, 67875}


def _ranked(items, seed: int, salt: str):
    """Deterministic ordering for reproducible sampling (no PRNG)."""
    return sorted(items, key=lambda item: hash((seed, salt, item)))


def _take(pool, n: int, seed: int, salt: str) -> list:
    return _ranked(pool, seed, salt)[:n]


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--batch-csv", default="reports/all-2026-11-02.csv")
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    hp = load_batch_hp_rows(SafePath(args.batch_csv, ROOT))
    by_cat = defaultdict(set)
    all_prs = set()
    for f in hp:
        cat = norm_category(f["category"])
        for n in f["prs"]:
            by_cat[cat].add(n)
            all_prs.add(n)

    picked = set(ANCHOR)
    cats = sorted(by_cat.keys())
    per_cat = max(3, args.n // max(1, len(cats)))
    for cat in cats:
        pool = sorted(by_cat[cat] - picked)
        picked.update(_take(pool, per_cat, args.seed, cat))

    for f in hp:
        if norm_category(f["category"]) in ("duplicate", "duplicate-backport", "stated-supersede"):
            if any(p in picked for p in f["prs"]):
                picked.update(f["prs"])

    remainder = sorted(all_prs - picked)
    for n in _take(remainder, max(0, args.n - len(picked)), args.seed, "remainder"):
        picked.add(n)

    sample = sorted(picked)[: args.n]
    out = SafePath(args.out, ROOT)
    out.mkdir(parents=True, exist_ok=True)
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
