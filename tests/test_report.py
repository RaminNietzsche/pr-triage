from triage.report import actionable_prs, build_findings, count_actionable_high_findings, group_of


def test_group_of_categories():
    assert group_of("merge-conflict") == "conflict"
    assert group_of("already-in-base (tentacle)") == "in-base"
    assert group_of("stacked") == "info"
    assert group_of("needs-rebase-label-but-clean") == "info"


def test_build_findings_ticket_closed(minimal_pr):
    rec = minimal_pr(100)
    rec.update({"component": "rgw", "base": "main", "body": "Fixes: https://tracker.ceph.com/issues/10001"})
    tickets = [{
        "number": 100,
        "closed": [{"id": 10001, "status": "Resolved", "closed_on": "2025-01-01T00:00:00Z"}],
        "all_closed": True,
        "relevant": [10001],
    }]
    findings = build_findings([rec], [], [], [], [], [], [], tickets)
    cats = [f["category"] for f in findings]
    assert "ticket-closed" in cats


def test_build_findings_skips_non_primary_ticket_closed(minimal_pr):
    rec = minimal_pr(101)
    rec.update({"component": "rgw", "base": "main", "body": "Validates the fix for https://tracker.ceph.com/issues/9999"})
    tickets = [{
        "number": 101,
        "closed": [{"id": 9999, "status": "Resolved", "closed_on": "2025-01-01T00:00:00Z"}],
        "all_closed": True,
        "relevant": [9999],
    }]
    findings = build_findings([rec], [], [], [], [], [], [], tickets)
    assert "ticket-closed" not in [f["category"] for f in findings]


def test_build_findings_merge_conflict(minimal_pr):
    rec = minimal_pr(200)
    rec.update({"component": "core", "base": "main"})
    stale = [{
        "number": 200,
        "conflicts": True,
        "conflict_files": ["src/foo.cc"],
        "needs_rebase_label": True,
        "days_since_update": 10,
        "files_gone_from_base": [],
        "n_files": 1,
        "inactive": False,
        "stale_label": False,
        "pinned": False,
        "gone_renamed_to": {},
        "gone_removed_by": {},
    }]
    findings = build_findings([rec], [], [], stale, [], [], [], [])
    assert any(f["category"] == "merge-conflict" for f in findings)
