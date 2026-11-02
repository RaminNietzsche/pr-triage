"""Run triage logic for one PR against a loaded KB snapshot."""

import time
from pathlib import Path

from kb.indexes import candidates_for
from triage.dupes import classify, clusters, embed, pr_text
from triage.fixed import already_fixed, backport_sources
from triage.gitdata import Git, analyse_pr, enrich_effective
from triage.report import build_findings
from triage.staleness import staleness
from triage.tracker_api import Tracker, ticket_findings
from triage.xref import cross_refs


def _pairs_for_target(target, by_n, indexes):
    cand_nums = candidates_for(target, indexes, by_n)
    cand_recs = [by_n[n] for n in cand_nums if by_n[n].get("enriched")]
    if not cand_recs:
        return []
    texts = [pr_text(r) for r in [target] + cand_recs]
    vecs, _method = embed(texts)
    pairs = []
    for j, other in enumerate(cand_recs, start=1):
        sim = float(vecs[0] @ vecs[j].T)
        c = classify(target, other, sim)
        if c:
            pairs.append(
                {
                    "a": target["number"],
                    "b": other["number"],
                    "base": target["base"],
                    "kind": c[0],
                    "confidence": c[1],
                    **c[2],
                }
            )
    return pairs


def _staleness_from_precomputed(target):
    """Rebuild staleness row from nightly KB merge/git fields when ``staleness`` dict absent."""
    pm = target.get("precomputed_merge") or {}
    g = target.get("git") or {}
    if not pm and g.get("conflicts") is None and not g.get("files"):
        return None
    from datetime import datetime, timezone

    upd = datetime.fromisoformat(target["updated_at"].replace("Z", "+00:00"))
    age = (datetime.now(timezone.utc) - upd).days
    return {
        "number": target["number"],
        "conflicts": pm.get("conflicts", g.get("conflicts", False)),
        "conflict_files": pm.get("conflict_files", g.get("conflict_files", []))[:10],
        "needs_rebase_label": "needs-rebase" in target.get("labels", []),
        "files_gone_from_base": [],
        "gone_renamed_to": {},
        "gone_removed_by": {},
        "n_files": len(g.get("files") or []),
        "days_since_update": age,
        "inactive": age > 365,
        "stale_label": "stale" in target.get("labels", []),
        "pinned": "pinned" in target.get("labels", []),
    }


def _staleness_for_target(target, git: Git | None):
    if git and target.get("enriched"):
        rows = staleness(git, [target])
        if rows:
            target["staleness"] = rows[0]
        return rows
    if target.get("staleness"):
        return [target["staleness"]]
    cached = _staleness_from_precomputed(target)
    if cached:
        return [cached]
    g = target.get("git") or {}
    if not g.get("files"):
        return []
    return [
        {
            "number": target["number"],
            "conflicts": g.get("conflicts", False),
            "conflict_files": g.get("conflict_files", [])[:10],
            "needs_rebase_label": "needs-rebase" in target.get("labels", []),
            "files_gone_from_base": [],
            "gone_renamed_to": {},
            "gone_removed_by": {},
            "n_files": len(g.get("files") or []),
            "days_since_update": 0,
            "inactive": False,
            "stale_label": "stale" in target.get("labels", []),
            "pinned": "pinned" in target.get("labels", []),
        }
    ]


def query_pr(snapshot: dict, pr_number: int, *, clone: str | None = None, no_tracker=False):
    """Return (findings, meta) using KB records; optional clone refreshes target git fields."""
    t0 = time.perf_counter()
    records = snapshot["records"]
    by_n = {r["number"]: r for r in records}
    open_numbers = set(by_n)
    if pr_number not in by_n:
        raise ValueError(f"PR #{pr_number} not in KB ({len(records)} open PRs)")

    target = dict(by_n[pr_number])
    git = Git(clone) if clone and Path(clone).is_dir() else None
    if git:
        info = analyse_pr(git, pr_number, target["base"])
        target["git"] = info
        target["enriched"] = not info.get("error")
        if not info.get("error"):
            enrich_effective(git, target)
            new = target["git"].get("commits_not_in_base", [])
            target["commit_authors"] = sorted(
                {x.strip().lower() for x in git.out("show", "-s", "--format=%an%n%ae", *new).splitlines() if x.strip()}
            ) if new else []

    indexes = snapshot.get("indexes") or {}
    pairs = _pairs_for_target(target, by_n, indexes) if target.get("enriched") else []
    cl = clusters(pairs)
    st = _staleness_for_target(target, git)
    fx, bp = ([], [])
    if git and target.get("enriched"):
        fx = already_fixed(git, [target])
        bp = backport_sources(git, [target])
    elif target.get("precomputed_fixed"):
        fx = [target["precomputed_fixed"]]
    if not bp and target.get("precomputed_backport"):
        bp = [target["precomputed_backport"]]

    xr = [x for x in cross_refs(records, open_numbers) if pr_number in (x["from"], x["to"])]

    tk = []
    if not no_tracker:
        tracker_root = snapshot.get("root") and (snapshot["root"] / "tracker")
        if tracker_root and tracker_root.is_dir():
            tk = ticket_findings(Tracker(tracker_root), [target])
        elif Path("data/tracker").is_dir():
            tk = ticket_findings(Tracker(Path("data/tracker")), [target])

    related = {pr_number}
    for p in pairs:
        related.update((p["a"], p["b"]))
    for x in xr:
        related.update((x["from"], x["to"]))
    recs_ctx = [by_n[n] for n in related if n in by_n]
    findings = build_findings(recs_ctx, pairs, cl, st, fx, xr, bp, tk)
    findings = [f for f in findings if pr_number in f["prs"]]
    elapsed = time.perf_counter() - t0
    meta = {
        "latency_s": elapsed,
        "n_candidates": len(candidates_for(target, indexes, by_n)) if target.get("enriched") else 0,
        "snapshot_at": snapshot.get("manifest", {}).get("built_at"),
        "enriched": target.get("enriched", False),
    }
    return findings, meta
