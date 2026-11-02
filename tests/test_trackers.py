from pathlib import Path

from pr_triage.config import TrackerConfig
from pr_triage.trackers.factory import get_tracker_adapter
from pr_triage.trackers.jira import JiraTracker
from pr_triage.trackers.none import NoneTracker


def test_none_tracker():
    t = NoneTracker()
    assert t.issue("1")["status"] == "disabled"


def test_jira_stub():
    t = JiraTracker(TrackerConfig(plugin="jira"), Path("/tmp/pr-triage-jira-test"))
    assert "stub" in t.issue("PROJ-1")["status"]


def test_factory_none():
    ad = get_tracker_adapter(TrackerConfig(plugin="none"), Path("/tmp/pr-triage-factory"))
    assert isinstance(ad, NoneTracker)
