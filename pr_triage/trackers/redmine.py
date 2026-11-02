"""Redmine REST adapter (tracker.ceph.com and similar)."""

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from pr_triage.config import TrackerConfig


class RedmineTracker:
    def __init__(self, cfg: TrackerConfig, cache_dir: Path):
        self.cfg = cfg
        self.dir = cache_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self._last = 0.0

    def issue(self, tid):
        f = self.dir / f"{tid}.json"
        if f.exists() and time.time() - f.stat().st_mtime < self.cfg.cache_max_age_s:
            return json.loads(f.read_text())
        wait = self.cfg.delay_s - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()
        base = self.cfg.base_url.rstrip("/")
        req = urllib.request.Request(
            f"{base}/issues/{tid}.json",
            headers={"User-Agent": self.cfg.user_agent},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.load(r)["issue"]
            rec = {
                "id": int(tid),
                "status": data["status"]["name"],
                "is_closed": data["status"].get("is_closed"),
                "tracker": data["tracker"]["name"],
                "project": data["project"]["name"],
                "subject": data.get("subject", ""),
                "closed_on": data.get("closed_on"),
                "updated_on": data.get("updated_on"),
            }
        except urllib.error.HTTPError as e:
            rec = {"id": int(tid), "status": f"HTTP {e.code}", "is_closed": None}
        except Exception as e:
            return {"id": int(tid), "status": f"error: {e}"[:80], "is_closed": None}
        f.write_text(json.dumps(rec))
        return rec

    def duplicate_of(self, tid):
        f = self.dir / f"{tid}.relations.json"
        if f.exists():
            return json.loads(f.read_text())
        time.sleep(self.cfg.delay_s)
        base = self.cfg.base_url.rstrip("/")
        req = urllib.request.Request(
            f"{base}/issues/{tid}.json?include=relations",
            headers={"User-Agent": self.cfg.user_agent},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                rel = json.load(r)["issue"].get("relations", [])
            out = [x["issue_to_id"] for x in rel if x["relation_type"] == "duplicates" and x["issue_id"] == int(tid)]
        except Exception:
            return []
        f.write_text(json.dumps(out))
        return out
