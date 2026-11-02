"""Parse tracker ticket numbers out of free text (patterns from triage config)."""
import re

from pr_triage.context import get_config

# A ticket is "primary" when the PR claims to fix/track it, not when it is cited as context.
_FIXES_HASH_RE = re.compile(r"(?i)\b(?:fix(?:es|ed)?|resolves?|closes?)\s*:?\s*#(\d+)\b")
_FIXES_GH_URL_RE = re.compile(
    r"(?i)\b(?:fix(?:es|ed)?|resolves?|closes?)\b\s*:?\s*(?:<)?"
    r"https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/issues/(\d+)"
)
_BARE_GH_ISSUE_LINE_RE = re.compile(
    r"(?i)^\W*https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/issues/(\d+)[\s,;>.()]*$"
)

_CONTEXT_TERMS = (
    "validate",
    "validates",
    "validates the",
    "validates the fix",
    "see also",
    "related to",
    "related",
    "context",
    "history",
    "discussed in",
    "continuation of",
    "depends on",
    "follow-up to",
    "follow-up for",
    "follows to",
    "follows for",
    "partial fix for",
    "alternative fix",
    "also fixes",
    "same bug as",
    "same issue as",
)
_CONTEXT_RES = tuple(re.compile(rf"(?i)\b{re.escape(term)}\b") for term in _CONTEXT_TERMS)


def _is_context_line(line: str) -> bool:
    return any(rx.search(line) for rx in _CONTEXT_RES)


def _issue_re():
    return re.compile(get_config().tracker.issue_id_regex, re.I)


def _primary_res():
    cfg = get_config()
    # Build primary line matcher from configured host/path in issue_id_regex
    pat = cfg.tracker.issue_id_regex
    inner = pat
    if "(" in pat:
        inner = pat.split("(", 1)[0].rstrip("\\")
    url_part = inner.replace("\\", "")
    return re.compile(
        rf"(?i)\b(?:fix(?:es|ed)?|resolves?|closes?|tracker)\b\s*:?\s*(?:<)?"
        rf"https?://{re.escape(url_part).replace(re.escape('https?://'), 'https?://')}(\d{{2,8}})"
    )


def _bare_re():
    cfg = get_config()
    pat = cfg.tracker.issue_id_regex
    inner = pat
    if "(" in pat:
        inner = pat.split("(", 1)[0].rstrip("\\")
    url_part = inner.replace("\\", "")
    return re.compile(rf"(?i)^\W*https?://{url_part}(\d{{2,8}})[\s.,;>)\]]*$")


def tickets(*texts):
    found = set()
    rx = _issue_re()
    for t in texts:
        found.update(rx.findall(t or ""))
    return sorted(found, key=lambda x: int(x) if str(x).isdigit() else x)


def _line_primary(line: str):
    line = line.strip()
    if not line:
        return []
    if _is_context_line(line) and not re.search(r"(?i)\b(?:fix(?:es|ed)?|resolves?|closes?)\s*:", line):
        return []
    out = _primary_res().findall(line)
    out.extend(_bare_re().findall(line))
    if out:
        return out
    # Generic: Fixes #123 or Fixes: https://github.com/org/repo/issues/123
    out = _FIXES_HASH_RE.findall(line)
    out.extend(_FIXES_GH_URL_RE.findall(line))
    out.extend(_BARE_GH_ISSUE_LINE_RE.findall(line))
    return out


def primary_tickets(*texts):
    found = set()
    for t in texts:
        for line in (t or "").splitlines():
            found.update(_line_primary(line))
    return sorted(found, key=lambda x: int(x) if str(x).isdigit() else x)


def primary_ticket_texts(rec):
    """Title, body, and commit messages used to detect primary tracker references."""
    g = rec.get("git") or {}
    return (rec.get("title"), rec.get("body"), g.get("new_commit_msgs", ""), g.get("commit_msgs", ""))
