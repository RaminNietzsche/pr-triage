#!/usr/bin/env python3
"""Run ~100-PR recall eval: agreement, drift split, latency, per-category metrics."""

import csv
import json
import statistics
import sys
import time
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
from triage.collect import load_list  # noqa: E402


def load_github_by_n(raw_dir: Path) -> dict:
    by = {}
    for pr in load_list(raw_dir):
        by[pr["number"]] = pr
    return by


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", required=True)
    ap.add_argument("--batch-csv", default="reports/all-2026-11-02.csv")
    ap.add_argument("--batch-meta", default="reports/batch-snapshot-2026-11-02.json")
    ap.add_argument("--sample", required=True, help="JSON from sample_recall_prs.py")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--raw", default="data/raw")
    ap.add_argument("--no-tracker", action="store_true", help="skip tracker (ticket-closed will not fire)")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    sample = json.loads(Path(args.sample).read_text())
    prs = sample["prs"]

    t_load = time.perf_counter()
    snap = load_snapshot(ROOT / args.kb)
    load_s = time.perf_counter() - t_load

    batch_hp = load_batch_hp_rows(ROOT / args.batch_csv)
    batch_by_pr = index_batch_by_pr(batch_hp)
    batch_meta = load_batch_snapshot(ROOT / args.batch_meta)
    github_by_n = load_github_by_n(ROOT / args.raw)

    latencies = []
    rows = []
    cold_model_s = None
    for i, n in enumerate(prs):
        t0 = time.perf_counter()
        rows.append(
            compare_one_pr(
                snap,
                batch_by_pr,
                n,
                batch_meta=batch_meta,
                github_by_n=github_by_n,
                no_tracker=args.no_tracker,
            )
        )
        qmeta = rows[-1]["query_meta"]
        latencies.append(qmeta.get("latency_s", time.perf_counter() - t0))
        if i == 0:
            cold_model_s = latencies[0]

    warm = latencies[1:] or latencies
    latency = {
        "snapshot_load_s": round(load_s, 4),
        "cold_query_s": round(cold_model_s or 0, 4),
        "warm_query_p50_s": round(statistics.median(warm), 4) if warm else None,
        "warm_query_p95_s": round(sorted(warm)[int(0.95 * (len(warm) - 1))], 4) if len(warm) > 1 else warm[0],
        "n_prs": len(prs),
    }

    agg = aggregate_totals(rows)
    by_cat = aggregate_by_category(rows)
    agreement = {"aggregate": agg, "by_category": by_cat, "per_pr": rows, "latency": latency, "sample": sample}
    (out_dir / "agreement.json").write_text(json.dumps(agreement, indent=2))

    csv_rows = []
    for r in rows:
        for md in r.get("miss_detail") or []:
            csv_rows.append(
                {
                    "pr": r["pr"],
                    "kind": "miss",
                    "category": md["key"][0],
                    "classification": md["classification"],
                    "base_tip_drift": r["drift"]["base_tip_drift"],
                    "head_sha_drift": r["drift"]["head_sha_drift"],
                }
            )
        for m in r["matches"]:
            csv_rows.append({"pr": r["pr"], "kind": "match", "category": m[0], "classification": "", "base_tip_drift": "", "head_sha_drift": ""})
    with open(out_dir / "agreement.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["pr", "kind", "category", "classification", "base_tip_drift", "head_sha_drift"])
        w.writeheader()
        w.writerows(csv_rows)

    with open(out_dir / "latency.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["pr", "latency_s"])
        for n, ls in zip(prs, latencies):
            w.writerow([n, f"{ls:.4f}"])

    print(json.dumps({"aggregate": agg, "latency": latency, "n_prs": len(prs)}, indent=2))


if __name__ == "__main__":
    main()
