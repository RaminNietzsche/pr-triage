"""Inverted indexes for fast per-PR candidate lookup."""

import subprocess
from collections import defaultdict

from triage.gitdata import base_ref


def build_indexes(records, max_file_fanout=300):
    patch_id = defaultdict(list)
    eff_patch = defaultdict(list)
    files = defaultdict(list)
    tickets = defaultdict(list)
    for r in records:
        n = r["number"]
        g = r.get("git") or {}
        for p in g.get("new_commit_patch_ids") or []:
            patch_id[p].append(n)
        ep = g.get("eff_patch_id")
        if ep:
            eff_patch[ep].append(n)
        for f in g.get("eff_files") or []:
            files[f].append(n)
        for t in r.get("new_tickets") or r.get("tickets") or []:
            tickets[str(t)].append(n)
    # drop mega-files from index (same rule as dupes.find_pairs)
    files = {k: v for k, v in files.items() if len(v) <= max_file_fanout}
    return {
        "patch_id": {k: sorted(set(v)) for k, v in patch_id.items()},
        "eff_patch": {k: sorted(set(v)) for k, v in eff_patch.items()},
        "file": {k: sorted(set(v)) for k, v in files.items()},
        "ticket": {k: sorted(set(v)) for k, v in tickets.items()},
    }


def candidates_for(target, indexes, by_number):
    """PR numbers that share a structural key with target (same base)."""
    n = target["number"]
    base = target["base"]
    g = target.get("git") or {}
    keys = (
        [("file", f) for f in g.get("eff_files") or []]
        + [("patch_id", p) for p in g.get("new_commit_patch_ids") or []]
        + [("eff_patch", g.get("eff_patch_id")) if g.get("eff_patch_id") else None]
        + [("ticket", t) for t in target.get("new_tickets") or target.get("tickets") or []]
    )
    out = set()
    for item in keys:
        if not item:
            continue
        kind, key = item
        bucket = indexes.get(kind, {}).get(key) or []
        for other in bucket:
            if other != n and by_number.get(other, {}).get("base") == base:
                out.add(other)
    return sorted(out)


def build_base_branch_patch_index(git, bases):
    """Patch-ids present on each base branch tip history (for already-in-base lookups)."""
    tips = {}
    base_patch = defaultdict(set)
    for base in sorted(set(bases)):
        ref = base_ref(base)
        if not git.has_ref(ref):
            continue
        tips[base] = git.out("rev-parse", "--short", ref).strip()
        proc_log = subprocess.Popen(
            ["git", "-C", git.dir, "log", "-p", "--format=commit %H", "--no-merges", ref],
            stdout=subprocess.PIPE,
            text=True,
            errors="replace",
        )
        proc_pid = subprocess.Popen(
            ["git", "-C", git.dir, "patch-id", "--stable"],
            stdin=proc_log.stdout,
            stdout=subprocess.PIPE,
            text=True,
            errors="replace",
        )
        proc_log.stdout.close()
        out, _ = proc_pid.communicate()
        for line in out.splitlines():
            parts = line.split()
            if parts:
                base_patch[parts[0]].add(base)
    return tips, {k: sorted(v) for k, v in base_patch.items()}
