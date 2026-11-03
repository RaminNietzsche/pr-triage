"""Staleness signals: conflicts with the base tip, files gone from the base, long inactivity."""
import os
from datetime import datetime, timezone

from pr_triage.context import get_config

from .gitdata import base_ref

# Max move / probably-moved entries shown in report reasons (standalone and folded).
MOVE_NOTE_DISPLAY_CAP = 5


def _rename_diff_flag() -> str:
    pct = get_config().thresholds.rename_similarity_percent
    pct = max(0, min(100, int(pct)))
    return f"-M{pct}%"


def _ls_tree_line(git, commit: str, path: str) -> tuple[str, str] | None:
    out = git.run("ls-tree", commit, "--", path, check=False).stdout.strip()
    if not out:
        return None
    parts = out.split()
    if len(parts) < 2:
        return None
    return parts[0], parts[1]


def _blob_size(git, commit: str, path: str) -> int:
    out = git.run("cat-file", "-s", f"{commit}:{path}", check=False).stdout.strip()
    if not out or not out.isdigit():
        return 0
    return int(out)


def _rename_pair_valid(git, commit: str, old_path: str, new_path: str, min_bytes: int) -> bool:
    parent = git.out("rev-parse", f"{commit}^").strip()
    old_info = _ls_tree_line(git, parent, old_path)
    new_info = _ls_tree_line(git, commit, new_path)
    if not old_info or not new_info:
        return False
    if old_info[1] == "commit" or new_info[1] == "commit":
        return False
    if old_info[0] == "120000" or new_info[0] == "120000":
        return False
    if _blob_size(git, parent, old_path) < min_bytes:
        return False
    if _blob_size(git, commit, new_path) < min_bytes:
        return False
    return True


def _deleting_commit(git, merge_base: str, tip: str, path: str) -> str | None:
    rev = f"{merge_base}..{tip}"
    sha = git.run(
        "log",
        "-1",
        "--diff-filter=D",
        "--format=%H",
        rev,
        "--",
        path,
        check=False,
    ).stdout.strip()
    return sha or None


def _rename_target_in_commit(git, commit: str, old_path: str) -> str | None:
    flag = _rename_diff_flag()
    ns = git.out("show", flag, "--find-renames", "--name-status", "--pretty=format:", commit)
    for line in ns.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if parts[0].startswith("R") and len(parts) >= 3 and parts[1] == old_path:
            return parts[2]
    return None


def _paths_added_since(git, merge_base: str, tip: str) -> frozenset[str]:
    """Paths newly present on *tip* since *merge_base* (adds and rename destinations)."""
    flag = _rename_diff_flag()
    added: set[str] = set()
    for line in git.out("diff", flag, "--find-renames", "--name-status", merge_base, tip).splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        code = parts[0]
        if code.startswith("A") and len(parts) >= 2:
            added.add(parts[-1])
        elif code.startswith("R") and len(parts) >= 3:
            added.add(parts[2])
    return frozenset(added)


def _path_ok_on_tip(git, tip: str, path: str, min_bytes: int) -> bool:
    info = _ls_tree_line(git, tip, path)
    if not info or info[1] != "blob":
        return False
    if info[0] == "120000":
        return False
    return _blob_size(git, tip, path) >= min_bytes


def _basename_added_candidates(
    git,
    tip: str,
    path: str,
    added_paths: frozenset[str],
    tip_files: frozenset[str],
    max_cands: int,
    min_bytes: int,
) -> list[str]:
    name = os.path.basename(path)
    cands = sorted(
        p
        for p in added_paths
        if os.path.basename(p) == name and p in tip_files and _path_ok_on_tip(git, tip, p, min_bytes)
    )
    if 1 <= len(cands) <= max_cands:
        return cands
    return []


def staleness(git, recs, now=None, inactive_days=None):
    if inactive_days is None:
        inactive_days = get_config().thresholds.inactive_days
    th = get_config().thresholds
    labels = get_config().labels
    min_blob = int(th.rename_min_blob_bytes)
    max_basename = int(th.basename_move_max_candidates)
    use_basename = th.basename_move_fallback
    now = now or datetime.now(timezone.utc)
    out = []
    for r in recs:
        g = r["git"]
        if not g.get("files"):
            continue
        btip = base_ref(r["base"])
        merge_base = g["merge_base"]
        tip_files = git.tree_files(btip)
        added_since = _paths_added_since(git, merge_base, btip) if use_basename else frozenset()
        new = g.get("commits_not_in_base", [])
        own = set(git.out("show", "--format=", "--name-only", *new).split()) if new else set()
        candidates = sorted(
            {
                f["old_path"]
                for f in g["files"]
                if f["status"] in "MDR" and f["old_path"] not in tip_files and f["old_path"] in own
            }
        )
        moved, probably_moved, gone = {}, {}, []
        removed_by = {}
        for path in candidates:
            del_commit = _deleting_commit(git, merge_base, btip, path)
            if del_commit:
                new_path = _rename_target_in_commit(git, del_commit, path)
                if new_path and new_path in tip_files and _rename_pair_valid(
                    git, del_commit, path, new_path, min_blob
                ):
                    moved[path] = new_path
                    continue
            if use_basename:
                cands = _basename_added_candidates(
                    git, btip, path, added_since, tip_files, max_basename, min_blob
                )
                if cands:
                    probably_moved[path] = cands
                    continue
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
