"""Local git analysis of PR heads (fetched as refs/pr/<N>) against their base branch.

Everything here is computed from a local clone; nothing is written to GitHub."""
import re
import subprocess
from functools import lru_cache

MAX_DIFF_BYTES = 20_000
MAX_COMMITS = 250


class Git:
    def __init__(self, repo_dir):
        self.dir = repo_dir

    def run(self, *args, check=True):
        p = subprocess.run(["git", "-C", self.dir, *args], capture_output=True, text=True, errors="replace")
        if check and p.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)}: {p.stderr.strip()[:300]}")
        return p

    def out(self, *args):
        return self.run(*args).stdout

    def has_ref(self, ref):
        return self.run("rev-parse", "--verify", "-q", ref, check=False).returncode == 0

    @lru_cache(maxsize=16)
    def tree_files(self, ref):
        return frozenset(self.out("ls-tree", "-r", "--name-only", ref).splitlines())


def base_ref(base):
    return f"refs/remotes/origin/{base}"


HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@", re.M)


def analyse_pr(git: Git, number: int, base: str):
    head, bref = f"refs/pr/{number}", base_ref(base)
    if not git.has_ref(head) or not git.has_ref(bref):
        return {"error": "missing ref"}
    mb = git.out("merge-base", bref, head).strip()
    commits = git.out("rev-list", "--reverse", f"{mb}..{head}").split()
    res = {"head_sha": git.out("rev-parse", head).strip(), "merge_base": mb,
           "n_commits": len(commits), "files": [], "hunks": {}, "commit_msgs": "", "diff": ""}
    if len(commits) > MAX_COMMITS:
        res["error"] = f"{len(commits)} commits vs base (probably wrong base); skipped"
        return res
    res["commit_msgs"] = git.out("log", "--format=%H%n%B%n----", f"{mb}..{head}")
    for line in git.out("diff", "--name-status", "-M", mb, head).splitlines():
        parts = line.split("\t")
        res["files"].append({"status": parts[0][0], "path": parts[-1], "old_path": parts[1]})
    diff = git.out("diff", "-U0", mb, head)
    res["hunks"] = parse_hunks(diff)  # pre-image line ranges, for overlap detection
    res["diff"] = diff[:MAX_DIFF_BYTES]
    res["diff_truncated"] = len(diff) > MAX_DIFF_BYTES
    res["patch_id"] = (subprocess.run(["git", "-C", git.dir, "patch-id", "--stable"], input=diff,
                                      capture_output=True, text=True).stdout.split() or [None])[0]
    # conflicts: simulate merging PR head into current base tip (git >= 2.38)
    mt = git.run("merge-tree", "--write-tree", "--name-only", "--no-messages", bref, head, check=False)
    res["conflicts"] = mt.returncode == 1
    res["conflict_files"] = mt.stdout.splitlines()[1:] if mt.returncode == 1 else []
    # commits whose patch is already in the base branch (git cherry: '-' = equivalent upstream)
    cherry = git.out("cherry", bref, head, mb).splitlines()
    res["commits_already_in_base"] = [c[2:] for c in cherry if c.startswith("- ")]
    res["commits_not_in_base"] = [c[2:] for c in cherry if c.startswith("+ ")]
    # cherry-pick sources (backports)
    res["cherry_picked_from"] = re.findall(r"cherry picked from commit ([0-9a-f]{40})", res["commit_msgs"])
    return res


def parse_hunks(diff):
    hunks, cur = {}, None
    for l in diff.splitlines():
        if l.startswith("--- "):
            cur = l[6:] if l.startswith("--- a/") else None
        m = HUNK_RE.match(l)
        if m and cur:
            s, n = int(m.group(1)), int(m.group(2) or 1)
            hunks.setdefault(cur, []).append((s, s + max(n, 1)))
    return hunks


def enrich_effective(git: Git, rec):
    """Add the PR's *effective* change: what merging it into the current base tip would change.

    Stale branches often still carry commits that already landed on the base;
    those must not count as overlap with other PRs. For conflicting PRs we fall
    back to the diff of the commits not yet in base (approximated by the
    merge-base diff restricted to files touched by those commits)."""
    g = rec["git"]
    if not g.get("files") or g.get("error"):
        return
    bref, head = base_ref(rec["base"]), f"refs/pr/{rec['number']}"
    new = set(g.get("commits_not_in_base", []))
    if not g.get("conflicts"):
        tree = git.run("merge-tree", "--write-tree", "--no-messages", bref, head, check=False).stdout.split()[0]
        diff = git.out("diff", "-U0", bref, tree)
        files = git.out("diff", "--name-only", bref, tree).split()
    else:
        touched = set()
        for c in new:
            touched.update(git.out("show", "--format=", "--name-only", c).split())
        diff = git.out("diff", "-U0", g["merge_base"], head, "--", *sorted(touched)) if touched else ""
        files = sorted(touched)
    g["eff_files"] = files
    g["eff_hunks"] = parse_hunks(diff)
    g["eff_patch_id"] = (subprocess.run(["git", "-C", git.dir, "patch-id", "--stable"], input=diff,
                                        capture_output=True, text=True).stdout.split() or [None])[0]
    # patch-ids of the commits that are not yet in base
    log = git.out("log", "-p", "--format=commit %H", "--no-merges", f"{g['merge_base']}..{head}") if new else ""
    pids = subprocess.run(["git", "-C", git.dir, "patch-id", "--stable"], input=log, capture_output=True, text=True).stdout
    g["new_commit_patch_ids"] = sorted({l.split()[0] for l in pids.splitlines() if l.split()[1] in new})
    g["new_commit_msgs"] = "\n".join(git.out("log", "-1", "--format=%B", c) for c in sorted(new)[:250])
    srcs = re.findall(r"cherry picked from commit ([0-9a-f]{40})", g["new_commit_msgs"])
    g["new_cherry_picked_from"] = sorted(set(srcs))
