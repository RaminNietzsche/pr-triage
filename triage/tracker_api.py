"""Ticket status lookups via configurable tracker plugins."""

from pathlib import Path

from pr_triage.context import get_config
from pr_triage.trackers import get_tracker_adapter


def _obsolete_status(cfg):
    return cfg.fix_landed_statuses | cfg.not_fixed_statuses


class Tracker:
    """Backward-compatible wrapper around a tracker adapter."""

    def __init__(self, cache_dir: Path, delay=1.0, max_age_s=24 * 3600):
        cfg = get_config().tracker
        self.dir = cache_dir
        self.delay = delay
        self.max_age = max_age_s
        self._adapter = get_tracker_adapter(cfg, cache_dir)

    def issue(self, tid):
        return self._adapter.issue(str(tid))

    def duplicate_of(self, tid):
        return self._adapter.duplicate_of(str(tid))


def duplicate_of(tracker: Tracker, tid):
    return tracker.duplicate_of(tid)


def _github_ticket_summary(tracker, git, rec, info, closed_payload):
    from .github_ticket import assess_github_closure, git_fix_commits_on_base, partial_fix_vs_pr

    by_id = {i["id"]: i for i in info}

    def other_open(n: int) -> bool:
        o = tracker.issue(str(n))
        return not o.get("is_closed")

    assessments = []
    merged_all = []
    for c in closed_payload:
        issue_rec = dict(by_id.get(c["id"]) or {})
        issue_rec["git_fix_commits"] = git_fix_commits_on_base(git, rec["base"], str(c["id"])) if git else []
        assess = assess_github_closure(issue_rec, other_issue_open=other_open)
        assess["issue_id"] = c["id"]
        assessments.append(assess)
        merged_all.extend(assess.get("merged_fix_prs") or issue_rec.get("merged_fix_prs") or [])

    pr_files = set(rec.get("git", {}).get("eff_files") or [])
    for path in rec.get("git", {}).get("files") or []:
        pr_files.add(path.get("path") or path.get("old_path") or "")

    partial = partial_fix_vs_pr(merged_all, {p for p in pr_files if p})

    emit_any = any(a.get("emit") for a in assessments)
    fix_proven = any(a.get("fix_proven") for a in assessments)
    overlap_proven = False
    if fix_proven and pr_files:
        fix_files: set[str] = set()
        for p in merged_all:
            fix_files.update(p.get("files") or [])
        overlap_proven = bool(pr_files & fix_files)

    if not emit_any:
        return {"emit": False}

    if partial:
        return {
            "emit": True,
            "confidence": "low",
            "kind": "ticket closed",
            "partial": partial,
            "fix_proven": overlap_proven,
        }

    if fix_proven and overlap_proven:
        kind = "fix reported landed"
        conf = "medium"
    else:
        kind = "ticket closed"
        conf = "low" if not fix_proven else "medium"

    notes = [a["note"] for a in assessments if a.get("note")]
    return {
        "emit": True,
        "confidence": conf,
        "kind": kind,
        "partial": None,
        "fix_proven": overlap_proven,
        "notes": notes,
    }


def ticket_findings(tracker: Tracker, recs, git=None):
    """PRs whose relevant linked tickets are all closed on the tracker."""
    from .tracker import primary_ticket_texts, primary_tickets

    tcfg = get_config().tracker
    obsolete_status = _obsolete_status(tcfg)
    is_github = tcfg.plugin in ("github_issues", "github")
    out = []
    for r in recs:
        tids = primary_tickets(*primary_ticket_texts(r))
        if not tids:
            continue
        info = [tracker.issue(t) for t in tids]
        backport = r["base"] in tcfg.release_branches
        rel = [
            i
            for i in info
            if (i.get("tracker") == tcfg.backport_tracker_name) == backport
            and i.get("is_closed") is not None
            and not i.get("status", "").startswith("QA")
        ]
        if not rel:
            continue
        closed = [i for i in rel if i["is_closed"] and i.get("status") in obsolete_status]
        if not closed:
            continue
        payload = [
            {
                "id": i["id"],
                "status": i["status"],
                "closed_on": i.get("closed_on"),
                "duplicate_of": duplicate_of(tracker, i["id"]) if i["status"] == "Duplicate" else [],
            }
            for i in closed
        ]
        entry = {
            "number": r["number"],
            "tickets": info,
            "relevant": [i["id"] for i in rel],
            "closed": payload,
            "all_closed": len(closed) == len(rel) and all(i["is_closed"] for i in rel),
        }
        if is_github:
            entry["github_summary"] = _github_ticket_summary(tracker, git, r, info, payload)
        out.append(entry)
    return out
