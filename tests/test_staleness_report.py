from triage.report import build_findings


def test_merge_conflict_notes_head_fork_deleted(minimal_pr):
    rec = minimal_pr(5232)
    rec.update({"component": "core", "base": "main", "head_fork_deleted": True})
    stale = [{
        "number": 5232,
        "conflicts": True,
        "conflict_files": ["src/requests/sessions.py"],
        "needs_rebase_label": False,
        "files_gone_from_base": [],
        "files_moved_on_base": {"requests/sessions.py": "src/requests/sessions.py"},
        "gone_renamed_to": {"requests/sessions.py": "src/requests/sessions.py"},
        "gone_removed_by": {},
        "n_files": 1,
        "inactive": True,
        "days_since_update": 400,
        "stale_label": False,
        "pinned": False,
    }]
    findings = build_findings([rec], [], [], stale, [], [], [], [])
    mc = next(f for f in findings if f["category"] == "merge-conflict")
    assert mc["reason"].startswith("head fork deleted;")
    assert "moved on base" in mc["reason"]
    assert not any(f["category"] == "files-gone" for f in findings)


def test_files_moved_without_conflict(minimal_pr):
    rec = minimal_pr(6454)
    rec.update({"component": "core", "base": "main"})
    stale = [{
        "number": 6454,
        "conflicts": False,
        "conflict_files": [],
        "needs_rebase_label": False,
        "files_gone_from_base": [],
        "files_moved_on_base": {"requests/utils.py": "src/requests/utils.py"},
        "gone_renamed_to": {},
        "gone_removed_by": {},
        "n_files": 2,
        "inactive": False,
        "days_since_update": 10,
        "stale_label": False,
        "pinned": False,
    }]
    findings = build_findings([rec], [], [], stale, [], [], [], [])
    assert any(f["category"] == "files-moved-on-base" for f in findings)
