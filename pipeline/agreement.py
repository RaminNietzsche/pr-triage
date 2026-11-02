"""Shared batch vs per-PR agreement metrics."""

from __future__ import annotations

from collections import defaultdict

from pipeline.drift import classify_miss, structural_context_drift
from pipeline.filter import filter_findings, is_high_precision
from pipeline.query import query_pr

STRUCTURAL_HP = frozenset({"merge-conflict", "files-gone", "already-in-base"})


def norm_category(cat: str) -> str:
    if cat.startswith("already-in-base"):
        return "already-in-base"
    return cat.split(" (")[0]


def finding_keys(f: dict, focus_pr: int) -> set[tuple]:
    cat = norm_category(f["category"])
    others = tuple(sorted(x for x in f["prs"] if x != focus_pr))
    return {(cat, others)}


def load_batch_hp_rows(csv_path):
    import csv

    from pr_triage.safepath import SafePath, allowed_base

    findings = []
    with SafePath(csv_path, allowed_base()).open(newline="") as fh:
        for row in csv.DictReader(fh):
            prs = [int(x.strip().lstrip("#")) for x in row["prs"].split() if x.strip()]
            findings.append(
                {
                    "category": row["category"],
                    "confidence": row["confidence"],
                    "prs": prs,
                    "reason": row.get("reason", ""),
                }
            )
    return [f for f in findings if is_high_precision(f)]


def index_batch_by_pr(findings):
    by = defaultdict(list)
    for f in findings:
        for n in f["prs"]:
            by[n].append(f)
    return by


def compare_one_pr(
    snap,
    batch_by_pr,
    n: int,
    *,
    batch_meta=None,
    github_by_n=None,
    refresh_clone: str | None = None,
    no_tracker: bool = True,
):
    by_n = {r["number"]: r for r in snap["records"]}
    rec = by_n.get(n, {})
    drift = structural_context_drift(
        n,
        rec.get("base", "main"),
        rec,
        kb_manifest=snap.get("manifest", {}),
        batch_meta=batch_meta or {},
        github_pull=(github_by_n or {}).get(n),
    )
    findings, meta = query_pr(
        snap,
        n,
        clone=refresh_clone,
        no_tracker=no_tracker,
    )
    per = filter_findings(findings)
    batch = batch_by_pr.get(n, [])
    per_keys = set()
    for f in per:
        per_keys |= finding_keys(f, n)
    batch_keys = set()
    for f in batch:
        batch_keys |= finding_keys(f, n)
    matches = per_keys & batch_keys
    misses = batch_keys - per_keys
    extras = per_keys - batch_keys
    miss_detail = [
        {
            "key": list(k),
            "classification": classify_miss(k, drift, structural_categories=STRUCTURAL_HP),
        }
        for k in sorted(misses)
    ]
    return {
        "pr": n,
        "matches": [list(k) for k in sorted(matches)],
        "misses": [list(k) for k in sorted(misses)],
        "extras": [list(k) for k in sorted(extras)],
        "miss_detail": miss_detail,
        "drift": drift,
        "per_n": len(per_keys),
        "batch_n": len(batch_keys),
        "query_meta": meta,
    }


def aggregate_by_category(rows):
    """TP/FN/FP per normalized high-precision category (batch = recall reference)."""
    cats = defaultdict(lambda: {"tp": 0, "fn": 0, "fn_drift": 0, "fn_real": 0, "fp": 0})
    for r in rows:
        matched_cats = {m[0] for m in r["matches"]}
        for m in r["matches"]:
            cats[m[0]]["tp"] += 1
        for md in r.get("miss_detail") or []:
            cat = md["key"][0]
            cats[cat]["fn"] += 1
            if md["classification"] == "drift":
                cats[cat]["fn_drift"] += 1
            else:
                cats[cat]["fn_real"] += 1
        for e in r["extras"]:
            cat = e[0]
            if cat not in matched_cats:
                cats[cat]["fp"] += 1
    summary = {}
    for cat, c in sorted(cats.items()):
        tp, fn, fp = c["tp"], c["fn"], c["fp"]
        recall = tp / (tp + fn) if (tp + fn) else None
        recall_adj = tp / (tp + c["fn_real"]) if (tp + c["fn_real"]) else None
        precision = tp / (tp + fp) if (tp + fp) else None
        summary[cat] = {**c, "recall": recall, "recall_drift_adjusted": recall_adj, "precision": precision}
    return summary


def aggregate_totals(rows):
    agg = {"matches": 0, "misses": 0, "extras": 0, "misses_drift": 0, "misses_real": 0}
    for r in rows:
        agg["matches"] += len(r["matches"])
        agg["misses"] += len(r["misses"])
        agg["extras"] += len(r["extras"])
        for md in r.get("miss_detail") or []:
            if md["classification"] == "drift":
                agg["misses_drift"] += 1
            else:
                agg["misses_real"] += 1
    return agg
