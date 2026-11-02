"""Minimal Jira stub: returns structured placeholders until a site URL is configured."""

from pathlib import Path

from pr_triage.config import TrackerConfig


class JiraTracker:
    def __init__(self, cfg: TrackerConfig, cache_dir: Path):
        self.cfg = cfg
        self.dir = cache_dir
        self.dir.mkdir(parents=True, exist_ok=True)

    def issue(self, tid: str) -> dict:
        return {
            "id": tid,
            "status": "jira-stub-not-configured",
            "is_closed": None,
            "tracker": "Jira",
        }

    def duplicate_of(self, tid: str) -> list:
        return []
