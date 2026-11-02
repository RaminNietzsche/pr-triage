#!/usr/bin/env python3
"""Compare batch CSV/Markdown totals against a baseline snapshot."""
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pr_triage.safepath import SafePath, resolve_under  # noqa: E402


def parse_md(path: SafePath) -> dict:
    text = path.read_text()
    m = re.search(r"Open PRs in [^:]+: (\d+); all open PRs analysed: \*\*(\d+)\*\*", text)
    open_n, analysed = (int(m.group(1)), int(m.group(2))) if m else (None, None)
    rows = re.findall(r"^\| ([^|]+) \| (\d+) \|", text, re.M)
    cats = {k.strip(): int(v) for k, v in rows if k.strip() and k.strip() != "category"}
    return {"open": open_n, "analysed": analysed, "categories": cats}


def count_csv(path: SafePath) -> int:
    with path.open() as f:
        return sum(1 for _ in csv.DictReader(f))


def main():
    baseline_md = SafePath(sys.argv[1] if len(sys.argv) > 1 else "reports/all-2026-11-02.md", ROOT)
    candidate_md = SafePath(sys.argv[2] if len(sys.argv) > 2 else "reports/all-latest.md", ROOT)
    b = parse_md(baseline_md)
    c = parse_md(candidate_md) if candidate_md.is_file() else {}
    print(json.dumps({"baseline": b, "candidate": c}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
