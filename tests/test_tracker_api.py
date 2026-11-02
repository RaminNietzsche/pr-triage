from pr_triage.context import get_config
from triage.tracker_api import ticket_findings


class FakeTracker:
    def __init__(self, issues):
        self.issues = issues
        self.dir = __import__("pathlib").Path("/tmp/fake-tracker-cache")

    def issue(self, tid):
        return self.issues[int(tid)]


def test_ticket_findings_requires_primary_fixes_line():
    rec = {
        "number": 1,
        "base": "main",
        "title": "fix",
        "body": "See also https://tracker.ceph.com/issues/1000",
        "git": {"new_commit_msgs": "", "commit_msgs": ""},
    }
    tr = FakeTracker({1000: {"id": 1000, "status": "Resolved", "is_closed": True, "tracker": "Bug"}})
    assert ticket_findings(tr, [rec]) == []


def test_ticket_findings_all_primary_closed():
    rec = {
        "number": 2,
        "base": "main",
        "title": "fix",
        "body": "Fixes: https://tracker.ceph.com/issues/2000",
        "git": {"new_commit_msgs": "", "commit_msgs": ""},
    }
    tr = FakeTracker({2000: {"id": 2000, "status": "Resolved", "is_closed": True, "tracker": "Bug"}})
    out = ticket_findings(tr, [rec])
    assert len(out) == 1
    assert out[0]["all_closed"]


def test_ticket_findings_ignores_non_obsolete_closed_status():
    rec = {
        "number": 3,
        "base": "main",
        "title": "fix",
        "body": "Fixes: https://tracker.ceph.com/issues/3000",
        "git": {"new_commit_msgs": "", "commit_msgs": ""},
    }
    tr = FakeTracker({3000: {"id": 3000, "status": "In Progress", "is_closed": False, "tracker": "Bug"}})
    assert ticket_findings(tr, [rec]) == []


def test_obsolete_status_sets_cover_tracker_workflow():
    cfg = get_config().tracker
    assert "Resolved" in cfg.fix_landed_statuses
    assert "Duplicate" in cfg.not_fixed_statuses
