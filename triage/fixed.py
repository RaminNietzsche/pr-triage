"""Already-fixed / already-merged detection (best effort).

1. git cherry: PR commits whose patch-id already exists on the base branch.
2. Tracker ticket: commits on the base branch (since the PR's merge-base) that
   reference the same tracker ticket, i.e. something else landed for that ticket."""
import re

from pr_triage.context import get_config

from .gitdata import base_ref
from .tracker import primary_ticket_texts, primary_tickets


def _min_cherry_share():
    return get_config().thresholds.min_cherry_share


def tracker_commits(git, base, merge_base, ticket):
    frag = get_config().tracker_grep_fragment()
    out = git.out("log", "--format=%H\x1f%cI\x1f%s\x1f%ae", f"--grep={frag}{ticket}\\b",
                  "-E", f"{merge_base}..{base_ref(base)}")
    return [dict(zip(("sha", "date", "subject", "author"), l.split("\x1f"))) for l in out.splitlines() if l]


def commit_files(git, sha):
    return set(git.out("show", "--format=", "--name-only", sha).split())


def patch_ids(git, shas):
    if not shas:
        return set()
    import subprocess
    log = git.out("show", "-p", "--format=commit %H", *shas)
    out = subprocess.run(["git", "-C", git.dir, "patch-id", "--stable"], input=log, capture_output=True, text=True).stdout
    return {l.split()[0] for l in out.splitlines()}


def already_fixed(git, recs):
    res = []
    for r in recs:
        g = r["git"]
        if not g.get("files") or not g.get("merge_base"):
            continue
        in_base, not_in = g.get("commits_already_in_base", []), g.get("commits_not_in_base", [])
        item = {"number": r["number"], "base": r["base"], "is_backport": r["base"] != "main",
                "tickets": r["new_tickets"], "commits_total": len(in_base) + len(not_in),
                "commits_already_in_base": in_base, "ticket_hits": []}
        pr_files = set(g.get("eff_files") or [f["path"] for f in g["files"]])
        own = patch_ids(git, in_base)  # base twins of the PR's own already-merged commits are not "other fixes"
        claim_tickets = primary_tickets(*primary_ticket_texts(r))
        for t in claim_tickets:
            for c in tracker_commits(git, r["base"], g["merge_base"], t):
                if own and patch_ids(git, [c["sha"]]) & own:
                    continue
                cf = commit_files(git, c["sha"])
                c.update(ticket=t, file_overlap=sorted(pr_files & cf)[:5])
                if c["file_overlap"]:  # precision review: same ticket on different files was 4/4 false positive
                    item["ticket_hits"].append(c)
        if in_base or item["ticket_hits"]:
            if in_base and not not_in:
                item["verdict"], item["confidence"] = "all commits already in base", "high"
            elif len(in_base) >= len(not_in):
                item["verdict"], item["confidence"] = "most commits already in base (branch carries merged work; needs rebase)", "medium"
            elif in_base:
                item["verdict"], item["confidence"] = "some commits already in base", "low"
            elif any(h["file_overlap"] for h in item["ticket_hits"]):
                if all(h["author"].lower() in r.get("commit_authors", ()) for h in item["ticket_hits"]):
                    continue  # author's own earlier commit for the ticket; almost always a follow-up
                item["verdict"], item["confidence"] = "same ticket fixed in base by another author, touching same files", "medium"
            share = len(in_base) / max(1, item["commits_total"])
            min_share = _min_cherry_share()
            if in_base and not not_in:
                pass  # all commits already in base; still subject to share thresholds below
            elif in_base and share < min_share and not item["ticket_hits"]:
                continue  # a few cherry-picked commits on a long branch are not "already landed"
            elif in_base and share < min_share and item.get("confidence") == "low" and not item["ticket_hits"]:
                continue
            res.append(item)
    return res


def release_branches():
    return get_config().tracker.release_branches


def resolve_to_main(git, sha, depth=3):
    """True if `sha`, or the commit its own 'cherry picked from' trailer names (recursively), is on main."""
    for _ in range(depth):
        if git.run("cat-file", "-e", f"{sha}^{{commit}}", check=False).returncode != 0:
            return False
        main = f"refs/remotes/origin/{get_config().github.default_base}"
        if git.run("merge-base", "--is-ancestor", sha, main, check=False).returncode == 0:
            return True
        m = re.findall(r"cherry picked from commit ([0-9a-f]{40})", git.out("log", "-1", "--format=%B", sha))
        if not m:
            return False
        sha = m[-1]
    return False


def backport_sources(git, recs):
    """For release-branch backports: are the cherry-picked source commits on main?"""
    out = []
    for r in recs:
        if r["base"] not in release_branches() or not r["git"].get("files"):
            continue
        srcs = r["git"].get("new_cherry_picked_from", [])
        main = f"refs/remotes/origin/{get_config().github.default_base}"
        missing = [c for c in srcs if git.run("merge-base", "--is-ancestor", c, main, check=False).returncode != 0]
        detail = []
        for c in missing:
            via = resolve_to_main(git, c)
            if via:  # e.g. cherry-picked from a tentacle backport whose own trailer points at main
                continue
            # first line only: --grep matches line by line
            subj = git.out("log", "-1", "--no-merges", "--format=%B", f"--grep=cherry picked from commit {c}",
                           f"refs/pr/{r['number']}").strip().split("\n")[0][:70]
            twin = git.out("log", "-1", "--no-merges", "--format=%h", "--fixed-strings", f"--grep={subj}",
                           main).strip() if subj else ""
            exists = git.run("cat-file", "-e", f"{c}^{{commit}}", check=False).returncode == 0
            on = [b for b in release_branches() if exists and git.run("merge-base", "--is-ancestor", c, f"refs/remotes/origin/{b}", check=False).returncode == 0]
            in_prs = [] if (on or not exists) else [int(x.split("/")[-1]) for x in git.out(
                "for-each-ref", "--contains", c, "--format=%(refname)", "refs/pr/").split()]
            detail.append({"sha": c, "subject": subj, "main_same_subject": twin, "on_release_branches": on,
                           "in_open_prs": [x for x in in_prs if x != r["number"]][:5]})
        missing = detail
        out.append({"number": r["number"], "base": r["base"], "n_sources": len(srcs), "missing_on_main": detail,
                    "no_cherry_pick_trailer": not srcs})
    return out
