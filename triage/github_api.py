"""Read-only GitHub REST access with on-disk caching.

Only GET requests are issued. Set GITHUB_TOKEN to raise the rate limit
(60/h anonymous, 5000/h authenticated)."""
import json
import os
import re
import time
import urllib.request
from pathlib import Path

API = "https://api.github.com"


def _get(url, tries=4):
    for i in range(tries):  # transient network errors (e.g. IncompleteRead) are retried with backoff
        try:
            return _get_once(url)
        except Exception as e:
            if i == tries - 1 or getattr(e, "code", 0) in (401, 403, 404, 422):
                raise
            print(f"  GET failed ({e.__class__.__name__}); retrying in {5 * 2 ** i}s")
            time.sleep(5 * 2 ** i)


def _user_agent() -> str:
    try:
        from pr_triage.context import get_config

        return get_config().tracker.user_agent
    except Exception:
        return "pr-triage (read-only)"


def _get_once(url):
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": _user_agent(),
        **({"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}"} if os.environ.get("GITHUB_TOKEN") else {}),
    })
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r), r.headers.get("Link", ""), int(r.headers.get("X-RateLimit-Remaining", "-1"))


def list_open_pulls(repo, cache_dir: Path, max_age_s=6 * 3600):
    """Return all open PRs of `repo` (list endpoint: metadata, labels, base/head, body)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    out, page = [], 1
    while True:
        f = cache_dir / f"pulls_open_p{page:03d}.json"
        if f.exists() and time.time() - f.stat().st_mtime < max_age_s:
            data = json.loads(f.read_text())
            more = len(data) == 100
        else:
            data, link, remaining = _get(f"{API}/repos/{repo}/pulls?state=open&per_page=100&page={page}&sort=created&direction=asc")
            f.write_text(json.dumps(data))
            more = 'rel="next"' in link
            print(f"  fetched page {page} ({len(data)} PRs, rate remaining {remaining})")
        out.extend(data)
        if not more or not data:
            break
        page += 1
    return out
