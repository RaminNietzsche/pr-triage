"""Batch triage run driven by TriageConfig."""

import json
from datetime import date
from pathlib import Path

from pr_triage.config import TriageConfig
from pr_triage.safepath import SafePath, allowed_base, resolve_under
from triage.collect import collect
from triage.dupes import clusters, find_pairs
from triage.fixed import already_fixed, backport_sources
from triage.github_api import list_open_pulls
from triage.gitdata import Git, base_ref, enrich_effective
from triage.report import (
    actionable_prs,
    build_findings,
    count_actionable_high_findings,
    write_csv,
    write_md,
)
from triage.staleness import staleness
from triage.tracker import primary_tickets, tickets
from triage.tracker_api import Tracker, ticket_findings
from triage.xref import cross_refs

DEFAULT_LIMITATIONS = [
    "Mergeability is simulated locally with `git merge-tree` against the base tip at snapshot time; GitHub's own mergeable flag was only spot-checked in precision reviews.",
    "Duplicate detection is heuristic. Text similarity of PR templates and boilerplate can inflate scores; low-confidence pairs often are related work, not duplicates.",
    "Cross-branch pairs (same change targeting main and a release branch) are treated as expected backport families and not reported as duplicates.",
    "'already-in-base' via git cherry only catches commits whose patch is textually equivalent; a fix rewritten differently is only caught via the tracker ticket when configured.",
    "Diffs larger than 20 KB are truncated for embedding; PRs with >250 commits ahead of base are skipped as probably mis-targeted.",
    "Inactivity uses GitHub `updated_at`, which also moves on label/bot activity, so it under-counts truly abandoned PRs.",
]


def _limitation_blurb(cfg: TriageConfig) -> list[str]:
    extra = list(cfg.limitations_extra)
    if cfg.tracker.plugin == "redmine":
        extra.insert(
            0,
            "Tracker tickets are parsed from configured tracker URLs; only 'primary' references "
            "(Fixes:/Resolves:/backport tracker:/bare URL line) are used for ticket status.",
        )
    elif cfg.tracker.plugin in ("github_issues", "github"):
        extra.insert(
            0,
            "Tracker tickets are parsed from GitHub issue references (Fixes #N / issue URLs).",
        )
    return DEFAULT_LIMITATIONS + extra


def run_batch(
    cfg: TriageConfig,
    *,
    component: str = "all",
    path_prefix: str | None = None,
    refresh: bool = False,
    no_tracker: bool = False,
    list_only: bool = False,
) -> dict:
    root = allowed_base()
    raw = resolve_under(cfg.paths.raw_dir, root)
    clone = cfg.github.clone_dir
    if path_prefix is None:
        if component == "all":
            path_prefix = ""
        else:
            path_prefix = cfg.path_prefix_template.format(component=component)
    allprs = list_open_pulls(cfg.github.repo, raw, max_age_s=0 if refresh else 10 ** 9)
    if list_only:
        return {"total_open": len(allprs), "list_only": True}
    prefix = path_prefix if path_prefix else f"src/{component}/" if component != "all" else ""
    prs_cache = SafePath(cfg.paths.prs_cache, root)
    recs, allrec, skipped = collect(raw, clone, prs_cache.path, component, prefix or "src/rgw/")
    recs = [r for r in recs if r["number"] not in skipped]
    if cfg.limits.max_prs_analyse:
        recs = sorted(recs, key=lambda r: r["updated_at"], reverse=True)[: cfg.limits.max_prs_analyse]
    git = Git(clone)
    for r in recs:
        enrich_effective(git, r)
        new = r["git"].get("commits_not_in_base", [])
        r["commit_authors"] = sorted(
            {x.strip().lower() for x in git.out("show", "-s", "--format=%an%n%ae", *new).splitlines() if x.strip()}
        ) if new else []
        r["new_tickets"] = tickets(r["title"], r["body"], r["git"].get("new_commit_msgs", ""))
        g = r["git"]
        r["primary_tickets"] = primary_tickets(r["title"], r["body"], g.get("new_commit_msgs", ""), g.get("commit_msgs", ""))
    pairs, method = find_pairs(recs)
    cl = clusters(pairs)
    st = staleness(git, recs)
    fx = already_fixed(git, recs)
    xr = cross_refs(recs, {r["number"] for r in recs})
    bp = backport_sources(git, recs)
    use_tracker = not no_tracker and cfg.tracker.plugin != "none"
    tk = (
        []
        if not use_tracker
        else ticket_findings(Tracker(resolve_under(cfg.paths.tracker_cache, root)), recs)
    )
    findings = build_findings(recs, pairs, cl, st, fx, xr, bp, tk)
    if cfg.enabled_categories:
        findings = [f for f in findings if f["category"] in cfg.enabled_categories]
    d = date.today().isoformat()
    resolve_under("reports", root).mkdir(exist_ok=True)
    scope = component
    if cfg.name and cfg.name not in ("ceph",):
        report_stem = f"{cfg.name}-{scope}"
    else:
        report_stem = scope
    SafePath(f"data/analysis-{report_stem}-{d}.json", root).write_text(
        json.dumps(
            {"tickets": tk, "backports": bp, "xrefs": xr, "pairs": pairs, "clusters": cl, "staleness": st, "fixed": fx, "findings": findings},
            indent=1,
        )
    )
    bases = sorted({r["base"] for r in recs})
    meta = {
        "total_open": len(allprs),
        "component": component,
        "path_prefix": prefix or "(all)",
        "n_backports": len(bp),
        "n_backports_no_trailer": sum(b["no_cherry_pick_trailer"] for b in bp),
        "bases": ", ".join(bases),
        "base_tips": ", ".join(f"{b}@{git.out('rev-parse', '--short', base_ref(b)).strip()}" for b in bases),
        "limitations": _limitation_blurb(cfg) + ([f"PR(s) {skipped} skipped: head ref not fetchable."] if skipped else []),
        "config": cfg.name,
        "repo": cfg.github.repo,
        "display_name": cfg.report.display_name,
        "tool_name": cfg.report.tool_name,
        "github_repo": cfg.github.repo,
    }
    write_md(resolve_under(f"reports/{report_stem}-{d}.md", root), d, recs, findings, cl, method, meta)
    write_csv(resolve_under(f"reports/{report_stem}-{d}.csv", root), findings, recs)
    if prs_cache.exists():
        cache = json.loads(prs_cache.read_text())
        by_n = {r["number"]: r for r in cache.get("all", [])}
        for r in recs:
            if r["number"] in by_n:
                by_n[r["number"]].update(
                    {
                        "primary_tickets": r.get("primary_tickets"),
                        "new_tickets": r.get("new_tickets"),
                        "commit_authors": r.get("commit_authors"),
                    }
                )
                g = r.get("git") or {}
                by_n[r["number"]]["git"].update(
                    {k: g[k] for k in (
                        "new_commit_msgs", "new_commit_patch_ids", "new_cherry_picked_from",
                        "eff_files", "eff_hunks", "eff_patch_id",
                    ) if k in g}
                )
        prs_cache.write_text(json.dumps(cache, indent=1))
    merge_high = sum(1 for f in findings if f["category"] == "merge-conflict" and f.get("confidence") == "high")
    return {
        "date": d,
        "scope": scope,
        "total_open": len(allprs),
        "analysed": len(recs),
        "findings": len(findings),
        "actionable_prs": len(actionable_prs(findings)),
        "actionable_high_findings": count_actionable_high_findings(findings),
        "merge_conflict_high": merge_high,
        "skipped": skipped,
        "report_md": f"reports/{report_stem}-{d}.md",
        "report_csv": f"reports/{report_stem}-{d}.csv",
    }
