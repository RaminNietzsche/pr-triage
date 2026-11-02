from pathlib import Path

from pr_triage.config import TrackerConfig

from .github_issues import GitHubIssuesTracker
from .jira import JiraTracker
from .none import NoneTracker
from .redmine import RedmineTracker


def get_tracker_adapter(cfg: TrackerConfig, cache_dir: Path):
    plugin = (cfg.plugin or "none").lower()
    if plugin == "none":
        return NoneTracker()
    if plugin == "redmine":
        return RedmineTracker(cfg, cache_dir)
    if plugin in ("github_issues", "github"):
        from pr_triage.context import get_config

        return GitHubIssuesTracker(cfg, cache_dir, repo=get_config().github.repo)
    if plugin == "jira":
        return JiraTracker(cfg, cache_dir)
    raise ValueError(f"Unknown tracker plugin: {cfg.plugin}")
