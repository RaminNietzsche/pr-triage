"""Markdown + CSV report writer."""
import csv
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

from pr_triage.safepath import SafePath, allowed_base, resolve_under


def _link(n, by):
    r = by[n]
    return f"[#{n}]({r['url']})"


def build_findings(recs, pairs, _clusters, stale, fixed, xrefs=(), backports=(), tickets=()):
    from pr_triage.context import get_config

    cfg = get_config()
    tcfg = cfg.tracker
    FIX_LANDED, NOT_FIXED = tcfg.fix_landed_statuses, tcfg.not_fixed_statuses
    if tcfg.base_url:
        tracker_label = urlparse(tcfg.base_url).netloc or tcfg.base_url
    elif tcfg.plugin in ("github_issues", "github"):
        tracker_label = f"{cfg.github.repo} issues"
    else:
        tracker_label = tcfg.plugin.replace("_", " ")
    by = {r["number"]: r for r in recs}
    F = []
    from .tracker import primary_ticket_texts, primary_tickets

    for t in tickets:
        if not t["closed"]:
            continue
        rec = by[t["number"]]
        claimed = set(primary_tickets(*primary_ticket_texts(rec)))
        rel_ids = {str(x) for x in t["relevant"]}
        if not claimed or not (claimed & rel_ids):
            continue
        sts = {c["status"] for c in t["closed"]}
        desc = ", ".join(f"#{c['id']} {c['status']}" + (f" of #{', #'.join(map(str, c['duplicate_of']))}" if c.get("duplicate_of") else "")
                         + (f" ({c['closed_on'][:10]})" if c.get("closed_on") else "") for c in t["closed"])
        if t["all_closed"]:
            if sts <= FIX_LANDED:
                kind = "fix reported landed"
            elif sts <= NOT_FIXED:
                kind = "closed without fix"
            else:
                kind = "closed"
            F.append({"category": "ticket-closed", "prs": [t["number"]], "confidence": "medium",
                      "reason": f"all {len(t['relevant'])} linked primary ticket(s) closed on {tracker_label}, {kind}: {desc}", "score": 1})
        else:
            F.append({"category": "ticket-partly-closed", "prs": [t["number"]], "confidence": "low",
                      "reason": f"{len(t['closed'])}/{len(t['relevant'])} primary tickets closed: {desc}", "score": 0})
    for b in backports:
        real = [d for d in b["missing_on_main"] if not d["main_same_subject"]]
        renamed = [d for d in b["missing_on_main"] if d["main_same_subject"]]
        if real:
            F.append({"category": "backport-source-not-on-main", "prs": [b["number"]], "confidence": "medium",
                      "reason": f"{len(real)}/{b['n_sources']} cherry-pick sources are not on main and no main commit has the same subject: "
                      + "; ".join(f"{d['sha'][:10]} \"{d['subject'][:60]}\"" + (f" (source commit is in open PR #{d['in_open_prs'][0]})" if d["in_open_prs"] else "")
                                  + (" (source SHA not found in any fetched ref; possibly a typo)" if not d["in_open_prs"] and not d["on_release_branches"] else "")
                                  for d in real[:3]), "score": len(real)})
        elif renamed:
            F.append({"category": "backport-trailer-sha-mismatch", "prs": [b["number"]], "confidence": "low",
                      "reason": "cherry-pick trailer SHA not on main, but main has a same-subject commit: "
                      + "; ".join(f"{d['sha'][:10]} -> main {d['main_same_subject']}" for d in renamed[:3]), "score": 0})
    for x in xrefs:
        F.append({"category": "stated-supersede", "prs": [x["from"], x["to"]], "confidence": x["confidence"],
                  "reason": f"#{x['from']} description says: \"{x['quote']}\" (both still open)", "score": 1.0})
    for p in pairs:
        ev = [p["why"], f"text sim {p['similarity']}", f"file Jaccard {p['file_jaccard']}"]
        if p["hunk_overlaps"]: ev.append(f"{p['hunk_overlaps']} overlapping hunks")
        if p["shared_tickets"]: ev.append("same tracker " + ",".join(p["shared_tickets"]))
        if p["shared_commits"]: ev.append(f"{p['shared_commits']} identical commits")
        if p["shared_cherry_picks"]: ev.append(f"{p['shared_cherry_picks']} shared cherry-pick sources")
        ev.append("same author" if p["same_author"] else f"authors {by[p['a']]['author']} / {by[p['b']]['author']}")
        F.append({"category": p["kind"], "prs": [p["a"], p["b"]], "confidence": p["confidence"],
                  "reason": "; ".join(ev), "score": p["similarity"]})
    for f in fixed:
        ev = []
        if f["commits_already_in_base"]:
            ev.append(f"{len(f['commits_already_in_base'])}/{f['commits_total']} commits have an equivalent patch on {f['base']} (git cherry)")
        for h in f["ticket_hits"][:3]:
            ev.append(f"{f['base']} commit {h['sha'][:10]} ({h['date'][:10]}) refs tracker {h['ticket']}: \"{h['subject'][:70]}\""
                      + (f" touching {', '.join(h['file_overlap'][:2])}" if h["file_overlap"] else ""))
        F.append({"category": "already-in-base" + (f" ({f['base']})" if f["is_backport"] else ""), "prs": [f["number"]],
                  "confidence": f["confidence"], "reason": f["verdict"] + ": " + "; ".join(ev),
                  "score": len(f["commits_already_in_base"]) / max(1, f["commits_total"])})
    for s in stale:
        if s["conflicts"]:
            F.append({"category": "merge-conflict", "prs": [s["number"]], "confidence": "high",
                      "reason": f"git merge-tree vs {by[s['number']]['base']} tip conflicts in {', '.join(s['conflict_files'][:3])}"
                      + (" (agrees with needs-rebase label)" if s["needs_rebase_label"] else " (no needs-rebase label yet)"),
                      "score": s["days_since_update"]})
        if s["needs_rebase_label"] and not s["conflicts"]:
            F.append({"category": "needs-rebase-label-but-clean", "prs": [s["number"]], "confidence": "low",
                      "reason": f"has needs-rebase label but git merge-tree merges it cleanly into {by[s['number']]['base']} tip"
                                " (GitHub's own mergeable flag may still disagree; verify before acting)",
                      "score": 0})
        if s["files_gone_from_base"]:
            allren = all(s["gone_renamed_to"].get(f) for f in s["files_gone_from_base"])
            F.append({"category": "files-gone", "prs": [s["number"]], "confidence": "medium" if allren else "high",
                      "reason": f"{len(s['files_gone_from_base'])}/{s['n_files']} touched files no longer exist on {by[s['number']]['base']}: "
                      + ", ".join(f + (f" (renamed to {s['gone_renamed_to'][f]})" if s["gone_renamed_to"].get(f) else f" (removed by {s['gone_removed_by'].get(f) or '?'})")
                                  for f in s["files_gone_from_base"][:3]), "score": len(s["files_gone_from_base"]) / s["n_files"]})
        if s["inactive"]:
            F.append({"category": "inactive>1y", "prs": [s["number"]], "confidence": "high",
                      "reason": f"no update for {s['days_since_update']} days" + (" (has stale label)" if s["stale_label"] else "")
                      + (" (but labelled pinned: kept open on purpose)" if s["pinned"] else ""),
                      "score": s["days_since_update"]})
    for f in F:
        f["component"] = by[f["prs"][0]].get("component", "other")
    return F


COMPONENT_GROUPS = {  # category groups for the per-component table
    "conflict": ("merge-conflict",), "files-gone": ("files-gone",), "inactive": ("inactive>1y",),
    "dup/compete": ("duplicate", "duplicate-backport", "competing-fix", "stated-supersede", "overlapping-backports"),
    "in-base": ("already-in-base",), "ticket": ("ticket-closed", "ticket-partly-closed"),
    "backport": ("backport-source-not-on-main", "backport-trailer-sha-mismatch"),
    "info": ("stacked", "shares-commits", "related-series", "possible-overlap", "needs-rebase-label-but-clean"),
}

# Informational-only categories (same set as the "info" row in COMPONENT_GROUPS).
INFORMATIONAL_CATEGORIES = frozenset(COMPONENT_GROUPS["info"])


def group_of(cat):
    for g, cats in COMPONENT_GROUPS.items():
        if any(cat == c or cat.startswith(c + " (") for c in cats):
            return g
    return "info"


def is_informational_category(category: str) -> bool:
    """True when a finding category is informational-only (not actionable for triage)."""
    return group_of(category) == "info"


def is_actionable_finding(finding: dict) -> bool:
    """A finding reviewers may act on: any confidence, non-informational category."""
    return not is_informational_category(finding["category"])


def is_actionable_high_finding(finding: dict) -> bool:
    """High-confidence actionable finding (excludes informational categories)."""
    return finding.get("confidence") == "high" and is_actionable_finding(finding)


def actionable_prs(findings) -> set[int]:
    """PR numbers with at least one actionable finding (primary batch headline metric)."""
    out: set[int] = set()
    for f in findings:
        if is_actionable_finding(f):
            out.update(f["prs"])
    return out


def count_actionable_high_findings(findings) -> int:
    return sum(1 for f in findings if is_actionable_high_finding(f))


def _prs_from_csv_row(row: dict) -> list[int]:
    return [int(x.lstrip("#")) for x in row["prs"].split()]


def actionable_prs_from_csv_rows(rows) -> set[int]:
    out: set[int] = set()
    for row in rows:
        if is_informational_category(row["category"]):
            continue
        out.update(_prs_from_csv_row(row))
    return out


def count_actionable_high_from_csv_rows(rows) -> int:
    return sum(
        1
        for row in rows
        if row.get("confidence") == "high" and not is_informational_category(row["category"])
    )


def component_table(recs, findings):
    prs = Counter(r.get("component", "other") for r in recs)
    flagged = {}
    grp = {}
    for f in findings:
        g = group_of(f["category"])
        grp.setdefault(f["component"], Counter())[g] += 1
        if is_actionable_finding(f):
            flagged.setdefault(f["component"], set()).update(f["prs"])
    rows = []
    for comp, n in prs.most_common():
        c = grp.get(comp, Counter())
        rows.append({"component": comp, "prs": n, "prs_flagged": len(flagged.get(comp, ())), "findings": sum(c.values()),
                     **{g: c[g] for g in COMPONENT_GROUPS}})
    return rows


def write_csv(path, findings, recs):
    safe = SafePath(path, allowed_base())
    by = {r["number"]: r for r in recs}
    with safe.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["category", "confidence", "component", "prs", "urls", "titles", "base", "reason"])
        for f in findings:
            w.writerow([f["category"], f["confidence"], f.get("component", ""), " ".join(f"#{n}" for n in f["prs"]),
                        " ".join(by[n]["url"] for n in f["prs"]), " || ".join(by[n]["title"] for n in f["prs"]),
                        "/".join(sorted({by[n]["base"] for n in f["prs"]})), f["reason"]])


def write_md(path, date, recs, findings, clusters_, method, meta):  # noqa: ARG001 clusters_ kept for API
    safe = SafePath(path, allowed_base())
    by = {r["number"]: r for r in recs}
    cnt = Counter((f["category"], f["confidence"]) for f in findings)
    cats = sorted({c for c, _ in cnt.items()})
    comp = meta.get("component", "rgw")
    allmode = comp == "all"
    if allmode:
        scope = f"all open PRs analysed: **{len(recs)}**"
    else:
        scope = f"{comp} PRs analysed: **{len(recs)}** (label `{comp}` or files under `{meta.get('path_prefix')}`)"
    n_actionable_prs = len(actionable_prs(findings))
    n_actionable_high = count_actionable_high_findings(findings)
    display = meta.get("display_name") or "Project"
    tool = meta.get("tool_name") or "pr-triage"
    gh_repo = meta.get("github_repo") or meta.get("repo") or "owner/repo"
    L = [f"# {display} open-PR triage report: {'all components' if allmode else comp} ({date})", "",
         f"Generated by {tool} (read-only; nothing was posted to GitHub). Findings are *candidates for human review*, not verdicts.", "",
         "## Scope", f"- Open PRs in {gh_repo}: {meta['total_open']}; {scope}. Base branches: {meta['bases']}.",
         f"- PRs with at least one actionable finding (non-informational category): **{n_actionable_prs}** "
         f"({n_actionable_high} high-confidence actionable findings).",
         f"- Data snapshot: PR list via GitHub REST, PR heads via `refs/pull/N/head`; base tips at {meta['base_tips']}.",
         f"- Release-branch backport PRs among them: {meta['n_backports']} ({meta['n_backports_no_trailer']} without any 'cherry picked from' trailer).",
         f"- Similarity method: {method}.", "", "## Counts by category", "", "| category | high | medium | low |", "|---|---|---|---|"]
    for c in cats:
        L.append(f"| {c} | {cnt[(c, 'high')]} | {cnt[(c, 'medium')]} | {cnt[(c, 'low')]} |")
    if allmode:
        rows = component_table(recs, findings)
        L += ["", "## By component", "",
              "Each PR is assigned one primary component: among its component labels, the one most of its files belong to (specific components before generic ones such as tests/documentation), or, without a component label, a guess from the paths it touches. "
              "A pair finding counts under its first PR. `flagged` = PRs with at least one non-informational finding.", "",
              "| component | PRs | flagged | " + " | ".join(COMPONENT_GROUPS) + " |", "|---|" + "---|" * (2 + len(COMPONENT_GROUPS))]
        for r in rows:
            L.append(f"| {r['component']} | {r['prs']} | {r['prs_flagged']} | " + " | ".join(str(r[g]) for g in COMPONENT_GROUPS) + " |")
    if clusters_:
        L += ["", "## Duplicate clusters (high/medium pairs, union-find)", ""]
        for g in clusters_:
            L.append("- " + ", ".join(f"[#{n}]({by[n]['url']}) {by[n]['title'][:60]}" for n in g))
    order = {"high": 0, "medium": 1, "low": 2}
    for c in cats:
        L += ["", f"## {c}", "", "| conf | PR(s) | base | title | evidence |", "|---|---|---|---|---|"]
        for f in sorted([f for f in findings if f["category"] == c], key=lambda f: (order[f["confidence"]], -f["score"])):
            L.append(f"| {f['confidence']} | {' '.join(_link(n, by) for n in f['prs'])} | {by[f['prs'][0]]['base']} | "
                     f"{' / '.join(by[n]['title'][:60].replace('|', '/') for n in f['prs'])} | {f['reason'].replace('|', '/')} |")
    L += ["", "## Method limitations", *[f"- {x}" for x in meta["limitations"]]]
    prec = SafePath(f"reports/precision-{date}.md", allowed_base())
    if prec.exists():
        L += ["", prec.read_text().rstrip()]
    safe.write_text("\n".join(L) + "\n")
