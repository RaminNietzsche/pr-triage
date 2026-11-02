#!/usr/bin/env python3
"""Compare per-PR high-precision findings vs batch report for a PR sample."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kb.load import load_snapshot  # noqa: E402
from pipeline.agreement import (  # noqa: E402
    aggregate_by_category,
    aggregate_totals,
    compare_one_pr,
    index_batch_by_pr,
    load_batch_hp_rows,
)
from pipeline.drift import load_batch_snapshot  # noqa: E402
from pr_triage.safepath import SafePath, resolve_under  # noqa: E402
from triage.collect import load_list  # noqa: E402


def main():
    import argparse
    import csv

    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", required=True)
    ap.add_argument("--batch-csv", default="reports/all-2026-11-02.csv")
    ap.add_argument("--batch-meta", default="reports/batch-snapshot-2026-11-02.json")
    ap.add_argument("--prs", nargs="*", type=int, help="PR numbers (default: read latency.csv pr column)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    snap = load_snapshot(resolve_under(args.kb, ROOT))
    batch_hp = load_batch_hp_rows(resolve_under(args.batch_csv, ROOT))
    batch_by_pr = index_batch_by_pr(batch_hp)
    batch_meta = load_batch_snapshot(resolve_under(args.batch_meta, ROOT))
    github_by_n = {}
    raw = resolve_under("data/raw", ROOT)
    if raw.is_dir() and list(raw.glob("pulls_open_p*.json")):
        for pr in load_list(raw):
            github_by_n[pr["number"]] = pr

    prs = args.prs
    if not prs:
        prs = []
        lat = resolve_under(args.out, ROOT).parent / "latency.csv"
        if lat.is_file():
            with open(lat, newline="") as fh:
                prs = [int(r["pr"]) for r in csv.DictReader(fh)]

    rows = [
        compare_one_pr(snap, batch_by_pr, n, batch_meta=batch_meta, github_by_n=github_by_n)
        for n in prs
    ]
    agg = aggregate_totals(rows)
    out = SafePath(args.out, ROOT)
    out.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {"aggregate": agg, "by_category": aggregate_by_category(rows), "per_pr": rows},
            indent=2,
        )
    )
    print(json.dumps({"aggregate": agg, "n_prs": len(rows)}, indent=2))


if __name__ == "__main__":
    main()
