#!/usr/bin/env python3
"""Diff two batch CSVs: category totals and finding keys; classify drift vs code change."""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pr_triage.safepath import SafePath, resolve_under  # noqa: E402


def normalize_reason(reason: str) -> str:
    """Strip volatile substrings (SHAs, day counts) for stable keys."""
    r = reason
    r = re.sub(r"\b[0-9a-f]{7,40}\b", "<sha>", r)
    r = re.sub(r"\b\d+ days\b", "<days>", r)
    r = re.sub(r"git merge-tree vs \S+ tip", "git merge-tree vs <base> tip", r)
    return r


def finding_key(row: dict) -> tuple:
    prs = tuple(sorted(int(x.lstrip("#")) for x in row["prs"].split()))
    return (row["category"], prs, normalize_reason(row.get("reason", "")))


def category_counts(rows: list[dict]) -> dict[str, dict[str, int]]:
    out: defaultdict[str, Counter] = defaultdict(Counter)
    for r in rows:
        out[r["category"]][r["confidence"]] += 1
    return {c: dict(cnt) for c, cnt in out.items()}


def load_csv(path: Path) -> list[dict]:
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("baseline", type=Path, default=Path("reports/all-2026-11-02.csv"), nargs="?")
    ap.add_argument("candidate", type=Path, default=Path("reports/all-latest.csv"), nargs="?")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    baseline = resolve_under(args.baseline, ROOT)
    candidate = resolve_under(args.candidate, ROOT)
    out_path = SafePath(args.out, ROOT) if args.out else None

    if not candidate.is_file():
        print(json.dumps({"error": f"missing candidate {candidate}"}, indent=2))
        return 1

    base_rows = load_csv(baseline)
    cand_rows = load_csv(candidate)
    base_keys = {finding_key(r): r for r in base_rows}
    cand_keys = {finding_key(r): r for r in cand_rows}

    only_base = set(base_keys) - set(cand_keys)
    only_cand = set(cand_keys) - set(base_keys)

    bc = category_counts(base_rows)
    cc = category_counts(cand_rows)
    all_cats = sorted(set(bc) | set(cc))
    cat_diff = {}
    for c in all_cats:
        b = bc.get(c, {})
        n = cc.get(c, {})
        for conf in ("high", "medium", "low"):
            if b.get(conf, 0) != n.get(conf, 0):
                cat_diff.setdefault(c, {})[conf] = {"baseline": b.get(conf, 0), "candidate": n.get(conf, 0)}

    # Heuristic: PR-set/category-only changes often drift; category renames = code
    drift_hints = []
    for k in list(only_base | only_cand)[:500]:
        cat, prs, _ = k
        other_side = only_cand if k in only_base else only_base
        same_prs = [x for x in other_side if x[1] == prs]
        if same_prs:
            drift_hints.append({"key": k, "same_prs_other_cat": [x[0] for x in same_prs[:3]]})

    report = {
        "baseline": str(baseline),
        "candidate": str(candidate),
        "findings": {"baseline": len(base_rows), "candidate": len(cand_rows)},
        "category_diff": cat_diff,
        "keys_only_baseline": len(only_base),
        "keys_only_candidate": len(only_cand),
        "sample_only_baseline": [str(k) for k in list(only_base)[:15]],
        "sample_only_candidate": [str(k) for k in list(only_cand)[:15]],
        "drift_hint_count": len(drift_hints),
    }
    text = json.dumps(report, indent=2)
    if out_path:
        out_path.write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
