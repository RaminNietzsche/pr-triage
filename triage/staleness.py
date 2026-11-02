"""Staleness signals: conflicts with the base tip, files gone from the base, long inactivity."""
import os
from datetime import datetime, timezone

from pr_triage.context import get_config

from .gitdata import base_ref


def _rename_diff_flag() -> str:
    pct = get_config().thresholds.rename_similarity_percent
    pct = max(0, min(100, int(pct)))
    return f"-M{pct}%"


def _base_path_moves(git, merge_base, tip):
    """Map old paths removed on the base branch to new paths (full diff, git rename detection)."""
    flag = _rename_diff_flag()
    ns = git.out("diff", flag, "--find-renames", "--name-status", "--diff-filter=RD", merge_base, tip)
    renamed, deleted = {}, set()
    for line in ns.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        code = parts[0]
        if code.startswith("R") and len(parts) >= 3:
            renamed[parts[1]] = parts[2]
        elif code.startswith("D") and len(parts) >= 2:
            deleted.add(parts[1])
    return renamed, deleted


def _basename_index(tip_files: frozenset[str]) -> dict[str, list[str]]:
    idx: dict[str, list[str]] = {}
    for path in tip_files:
        idx.setdefault(os.path.basename(path), []).append(path)
    for name in idx:
        idx[name].sort()
    return idx


def _basename_candidates(path: str, tip_files: frozenset[str], basename_idx: dict[str, list[str]]) -> list[str]:
    name = os.path.basename(path)
    return [p for p in basename_idx.get(name, []) if p != path]


def staleness(git, recs, now=None, inactive_days=None):
    if inactive_days is None:
        inactive_days = get_config().thresholds.inactive_days
    labels = get_config().labels
    use_basename = get_config().thresholds.basename_move_fallback
    now = now or datetime.now(timezone.utc)
    out = []
    for r in recs:
        g = r["git"]
        if not g.get("files"):
            continue
        btip = base_ref(r["base"])
        tip_files = git.tree_files(btip)
        basename_idx = _basename_index(tip_files) if use_basename else {}
        new = g.get("commits_not_in_base", [])
        own = set(git.out("show", "--format=", "--name-only", *new).split()) if new else set()
        candidates = sorted(
            {
                f["old_path"]
                for f in g["files"]
                if f["status"] in "MDR" and f["old_path"] not in tip_files and f["old_path"] in own
            }
        )
        renamed_on_base, deleted_on_base = _base_path_moves(git, g["merge_base"], btip)
        moved, probably_moved, gone = {}, {}, []
        removed_by = {}
        for path in candidates:
            new_path = renamed_on_base.get(path)
            if new_path and new_path in tip_files:
                moved[path] = new_path
                continue
            if use_basename:
                cands = _basename_candidates(path, tip_files, basename_idx)
                if cands:
                    probably_moved[path] = cands
                    continue
            if path in deleted_on_base or path not in tip_files:
                gone.append(path)
        for f in gone:
            c = git.out(
                "log", "-1", "--diff-filter=D", "--format=%h %cs %s", btip, "--", f
            ).strip()
            removed_by[f] = c[:90]
        upd = datetime.fromisoformat(r["updated_at"].replace("Z", "+00:00"))
        age = (now - upd).days
        out.append(
            {
                "number": r["number"],
                "conflicts": g.get("conflicts", False),
                "conflict_files": g.get("conflict_files", [])[:10],
                "needs_rebase_label": labels.needs_rebase in r["labels"],
                "files_gone_from_base": gone,
                "files_moved_on_base": moved,
                "files_probably_moved_on_base": probably_moved,
                "gone_renamed_to": moved,
                "gone_removed_by": removed_by if gone else {},
                "n_files": len(g["files"]),
                "days_since_update": age,
                "inactive": age > inactive_days,
                "stale_label": labels.stale in r["labels"],
                "pinned": labels.pinned in r["labels"],
            }
        )
    return out
