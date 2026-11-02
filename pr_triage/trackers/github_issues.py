"""GitHub Issues adapter: uses the same repo's issue tracker via REST API."""

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from pr_triage.config import TrackerConfig


class GitHubIssuesTracker:
    def __init__(self, cfg: TrackerConfig, cache_dir: Path, repo: str | None = None):
        self.cfg = cfg
        self.dir = cache_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.repo = repo or os.environ.get("PR_TRIAGE_GITHUB_REPO", "")
        self._last = 0.0

    def _headers(self):
        h = {"User-Agent": self.cfg.user_agent, "Accept": "application/vnd.github+json"}
        tok = os.environ.get("GITHUB_TOKEN")
        if tok:
            h["Authorization"] = f"Bearer {tok}"
        return h

    def issue(self, tid):
        f = self.dir / f"gh-{tid}.json"
        if f.exists() and time.time() - f.stat().st_mtime < self.cfg.cache_max_age_s:
            return json.loads(f.read_text())
        if not self.repo:
            return {"id": int(tid), "status": "no repo configured", "is_closed": None}
        wait = self.cfg.delay_s - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()
        url = f"https://api.github.com/repos/{self.repo}/issues/{tid}"
        req = urllib.request.Request(url, headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.load(r)
            closed = data.get("state") == "closed"
            rec = {
                "id": int(tid),
                "status": "Closed" if closed else "Open",
                "is_closed": closed,
                "tracker": "GitHub Issue",
                "project": self.repo,
                "subject": data.get("title", ""),
                "closed_on": data.get("closed_at"),
                "updated_on": data.get("updated_at"),
            }
        except urllib.error.HTTPError as e:
            rec = {"id": int(tid), "status": f"HTTP {e.code}", "is_closed": None}
        except Exception as e:
            return {"id": int(tid), "status": f"error: {e}"[:80], "is_closed": None}
        f.write_text(json.dumps(rec))
        return rec

    def duplicate_of(self, tid: str) -> list:
        return []
