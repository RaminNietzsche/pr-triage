"""Git-enrich a subset of PRs for KB build (read-only local clone).

Nightly enrich runs the same structural analysis as batch triage for each PR:
``analyse_pr`` (merge-tree vs current base tip) plus ``staleness`` (conflicts,
files-gone, inactivity). Results are stored on each record as ``staleness`` /
``precomputed_merge`` and written to ``prs.jsonl`` by ``kb.build.build_snapshot``.
"""

from pathlib import Path

from triage.collect import clean_body
from triage.gitdata import Git, analyse_pr, enrich_effective
from triage.fixed import already_fixed, backport_sources
from triage.staleness import staleness
from triage.tracker import primary_tickets, tickets


def enrich_prs(raw_dir: Path, clone: str, numbers: list[int] | None = None):
    """Return full PR records with git analysis for given numbers (or all in raw list)."""
    from triage.collect import load_list

    git = Git(clone)
    prs = load_list(raw_dir)
    want = set(numbers) if numbers else None
    out = []
    for pr in prs:
        n = pr["number"]
        if want is not None and n not in want:
            continue
        try:
            info = analyse_pr(git, n, pr["base"]["ref"])
        except Exception as e:
            info = {"error": str(e)[:300]}
        rec = {
            "number": n,
            "url": pr["html_url"],
            "title": pr["title"],
            "body": clean_body(pr["body"]),
            "author": pr["user"]["login"],
            "created_at": pr["created_at"],
            "updated_at": pr["updated_at"],
            "base": pr["base"]["ref"],
            "draft": pr.get("draft", False),
            "labels": [l["name"] for l in pr["labels"]],
            "head_sha": info.get("head_sha"),
            "git": info,
            "enriched": not info.get("error"),
        }
        if not info.get("error"):
            enrich_effective(git, rec)
            rec["precomputed_merge"] = {
                "conflicts": rec["git"].get("conflicts"),
                "conflict_files": rec["git"].get("conflict_files", [])[:10],
            }
            new = rec["git"].get("commits_not_in_base", [])
            rec["commit_authors"] = sorted(
                {x.strip().lower() for x in git.out("show", "-s", "--format=%an%n%ae", *new).splitlines() if x.strip()}
            ) if new else []
        rec["new_tickets"] = tickets(pr["title"], pr["body"], info.get("new_commit_msgs") or info.get("commit_msgs", ""))
        rec["primary_tickets"] = primary_tickets(pr["title"], pr["body"], info.get("new_commit_msgs") or info.get("commit_msgs", ""))
        from triage.components import primary_component

        rec["component"], rec["component_source"] = primary_component(rec)
        out.append(rec)
    if out:
        by_n = {r["number"]: r for r in out}
        for s in staleness(git, out):
            by_n[s["number"]]["staleness"] = s
        for fx in already_fixed(git, out):
            by_n[fx["number"]]["precomputed_fixed"] = fx
        for bp in backport_sources(git, out):
            by_n[bp["number"]]["precomputed_backport"] = bp
    return out
