from triage.report import build_findings


def test_probably_moved_reason_text(minimal_pr):
    rec = minimal_pr(5693)
    rec.update({"component": "core", "base": "main"})
    stale = [{
        "number": 5693,
        "conflicts": True,
        "conflict_files": ["src/requests/compat.py"],
        "needs_rebase_label": False,
        "files_gone_from_base": [],
        "files_moved_on_base": {},
        "files_probably_moved_on_base": {
            "requests/compat.py": ["src/requests/compat.py", "tests/compat.py"],
        },
        "gone_renamed_to": {},
        "gone_removed_by": {},
        "n_files": 5,
        "inactive": True,
        "days_since_update": 400,
        "stale_label": False,
        "pinned": False,
    }]
    findings = build_findings([rec], [], [], stale, [], [], [], [])
    mc = next(f for f in findings if f["category"] == "merge-conflict")
    assert "probably moved (same filename found at" in mc["reason"]
    assert "src/requests/compat.py" in mc["reason"]
    assert not any(f["category"] == "files-gone" for f in findings)
