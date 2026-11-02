#!/usr/bin/env python3
"""Summarize Ceph batch totals for regression notes (read-only compare to baseline)."""
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pr_triage.safepath import resolve_under  # noqa: E402
from triage.report import (  # noqa: E402
    actionable_prs_from_csv_rows,
    count_actionable_high_from_csv_rows,
)

BASELINE_MD = resolve_under("reports/all-2026-11-02.md", ROOT)
BASELINE_CSV = resolve_under("reports/all-2026-11-02.csv", ROOT)


def md_totals(path: Path):
    t = path.read_text()
    m = re.search(r"Open PRs in [^:]+: (\d+); all open PRs analysed: \*\*(\d+)\*\*", t)
    return {"open": int(m.group(1)), "analysed": int(m.group(2))} if m else {}


def csv_totals(path: Path):
    rows = list(csv.DictReader(path.open()))
    return {
        "findings": len(rows),
        "merge_conflict_high": sum(1 for r in rows if r.get("category") == "merge-conflict" and r.get("confidence") == "high"),
        "actionable_prs": len(actionable_prs_from_csv_rows(rows)),
        "actionable_high_findings": count_actionable_high_from_csv_rows(rows),
    }


def main():
    b = {**md_totals(BASELINE_MD), **csv_totals(BASELINE_CSV)}
    print("baseline", b)
    expected = {
        "open": 1855,
        "analysed": 1854,
        "findings": 694,
        "actionable_prs": 361,
        "actionable_high_findings": 340,
        "merge_conflict_high": 300,
    }
    print("expected (2026-11-02 regenerate)", expected)
    for k in expected:
        if k in b and b[k] != expected[k]:
            print(f"delta {k}: baseline file {b[k]} vs documented {expected[k]}")


if __name__ == "__main__":
    main()
