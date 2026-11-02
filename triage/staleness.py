"""Staleness signals: conflicts with the base tip, files gone from the base, long inactivity."""
from datetime import datetime, timedelta, timezone

from pr_triage.context import get_config

from .gitdata import base_ref


def staleness(git, recs, now=None, inactive_days=None):
    if inactive_days is None:
        inactive_days = get_config().thresholds.inactive_days
    labels = get_config().labels
    now = now or datetime.now(timezone.utc)
    out = []
    for r in recs:
        g = r["git"]
        if not g.get("files"):
            continue
        tip_files = git.tree_files(base_ref(r["base"]))
        # files the PR modifies/deletes/renames that no longer exist at the base tip
        new = g.get("commits_not_in_base", [])
        own = set(git.out("show", "--format=", "--name-only", *new).split()) if new else set()
        # only files touched by the PR's own not-yet-merged commits count
        gone = sorted({f["old_path"] for f in g["files"] if f["status"] in "MDR" and f["old_path"] not in tip_files
                       and f["old_path"] in own})
        moved, removed_by = {}, {}
        if gone:
            ns = git.out("diff", "-M", "--name-status", "--diff-filter=RD", g["merge_base"], base_ref(r["base"]), "--", *gone)
            for line in ns.splitlines():
                parts = line.split("\t")
                moved[parts[1]] = parts[2] if parts[0].startswith("R") else None
        removed_by = {}
        for f in gone:
            if not moved.get(f):
                c = git.out("log", "-1", "--diff-filter=D", "--format=%h %cs %s", base_ref(r["base"]), "--", f).strip()
                removed_by[f] = c[:90]
        upd = datetime.fromisoformat(r["updated_at"].replace("Z", "+00:00"))
        age = (now - upd).days
        out.append({"number": r["number"], "conflicts": g.get("conflicts", False),
                    "conflict_files": g.get("conflict_files", [])[:10], "needs_rebase_label": labels.needs_rebase in r["labels"],
                    "files_gone_from_base": gone, "gone_renamed_to": moved, "gone_removed_by": removed_by if gone else {}, "n_files": len(g["files"]),
                    "days_since_update": age, "inactive": age > inactive_days, "stale_label": labels.stale in r["labels"], "pinned": labels.pinned in r["labels"]})
    return out
