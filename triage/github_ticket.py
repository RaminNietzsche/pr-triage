"""GitHub Issues closure semantics for ticket-closed findings (not Redmine)."""
from __future__ import annotations

import re

_CLOSE_FAVOR_RE = re.compile(
    r"(?i)(?:clos(?:ing|ed)\s+(?:in\s+)?favor\s+of|duplicate\s+of|consolidat(?:e|ing)\s+(?:into|with))\s*#(\d+)"
)
_STALE_SWEEP_RE = re.compile(r"(?i)\b(stale|sweep|inactiv(?:e|ity)|auto[- ]?clos)")
_NOT_BUG_RE = re.compile(r"(?i)\bnot\s+a\s+bug\b")


def _merged_fix_prs(issue_rec: dict) -> list[dict]:
    return [p for p in issue_rec.get("merged_fix_prs") or [] if p.get("number")]


def _issue_text_blob(issue_rec: dict) -> str:
    parts = [issue_rec.get("subject") or "", issue_rec.get("body") or ""]
    for c in issue_rec.get("closing_comments") or []:
        parts.append(c)
    return "\n".join(parts)


def assess_github_closure(issue_rec: dict, *, other_issue_open) -> dict:
    """Return assessment used by report/ticket_findings for one closed GitHub issue."""
    merged = _merged_fix_prs(issue_rec)
    blob = _issue_text_blob(issue_rec)
    state_reason = (issue_rec.get("state_reason") or "").lower()
    favor = _CLOSE_FAVOR_RE.search(blob)
    if favor:
        target = int(favor.group(1))
        if other_issue_open(target):
            return {
                "emit": False,
                "kind": "closed without fix",
                "confidence": None,
                "fix_proven": False,
                "note": f"closed in favor of #{target} (still open)",
            }
    if _NOT_BUG_RE.search(blob) or state_reason == "not_planned":
        return {
            "emit": False,
            "kind": "closed without fix",
            "confidence": None,
            "fix_proven": False,
            "note": "closed as not planned / not a bug",
        }
    if _STALE_SWEEP_RE.search(blob):
        return {
            "emit": False,
            "kind": "closed without fix",
            "confidence": None,
            "fix_proven": False,
            "note": "stale-issue sweep closure",
        }
    git_commits = issue_rec.get("git_fix_commits") or []
    if git_commits:
        for c in git_commits:
            merged.append({"number": None, "files": c.get("files") or [], "sha": c.get("sha")})
    if not merged and state_reason != "completed":
        return {
            "emit": True,
            "kind": "ticket closed",
            "confidence": "low",
            "fix_proven": False,
            "note": "",
            "merged_fix_prs": [],
        }
    if not merged:
        return {
            "emit": True,
            "kind": "ticket closed",
            "confidence": "medium",
            "fix_proven": False,
            "note": "no merged PR or fix commit on base",
            "merged_fix_prs": [],
        }
    return {
        "emit": True,
        "kind": "fix reported landed",
        "confidence": "medium",
        "fix_proven": True,
        "note": "",
        "merged_fix_prs": merged,
    }


def git_fix_commits_on_base(git, base: str, tid: str) -> list[dict]:
    """Commits on the base branch that claim to fix/close the issue."""
    if not git:
        return []
    from .gitdata import base_ref

    bref = base_ref(base)
    out = []
    seen: set[str] = set()
    for needle in (f"Fixes #{tid}", f"Closes #{tid}", f"Resolves #{tid}"):
        for sha in git.out("log", "--format=%H", bref, f"--grep={needle}").splitlines():
            sha = sha.strip()
            if not sha or sha in seen:
                continue
            seen.add(sha)
            files = git.out("show", "--format=", "--name-only", sha).split()
            out.append({"sha": sha, "files": files})
    return out


def partial_fix_vs_pr(merged_prs: list[dict], pr_files: set[str]) -> dict | None:
    """When fix PRs exist, compare touched files with the open PR."""
    if not merged_prs or not pr_files:
        return None
    fix_files: set[str] = set()
    for p in merged_prs:
        fix_files.update(p.get("files") or [])
    if not fix_files:
        return None
    overlap = pr_files & fix_files
    extra = pr_files - fix_files
    if overlap and extra:
        return {
            "category": "ticket-partly-superseded",
            "confidence": "low",
            "overlap": sorted(overlap),
            "extra": sorted(extra),
            "fix_prs": [p["number"] for p in merged_prs],
        }
    return None
