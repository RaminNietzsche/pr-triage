import json
from pathlib import Path

from kb.build import build_snapshot
from kb.load import load_snapshot
from pipeline.query import query_pr


def _staleness_row(number, *, conflicts=False, gone=None):
    gone = gone or []
    return {
        "number": number,
        "conflicts": conflicts,
        "conflict_files": ["src/x.cc"] if conflicts else [],
        "needs_rebase_label": False,
        "files_gone_from_base": gone,
        "gone_renamed_to": {},
        "gone_removed_by": {f: "abc dead" for f in gone},
        "n_files": 5,
        "days_since_update": 10,
        "inactive": False,
        "stale_label": False,
        "pinned": False,
    }


def test_build_snapshot_persists_staleness(tmp_path, minimal_pr, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r1 = minimal_pr(62401, eff_files=["a.cc"])
    r1.update(
        {
            "url": "https://github.com/ceph/ceph/pull/62401",
            "updated_at": "2025-06-01T00:00:00Z",
            "labels": ["needs-rebase"],
            "staleness": _staleness_row(62401, conflicts=True, gone=["src/old.cc"]),
            "precomputed_merge": {"conflicts": True, "conflict_files": ["src/x.cc"]},
            "git": {
                **r1["git"],
                "conflicts": True,
                "conflict_files": ["src/x.cc"],
                "files": [{"status": "M", "path": "a.cc", "old_path": "a.cc"}],
            },
        }
    )
    raw = Path("raw")
    raw.mkdir()
    (raw / "pulls_open_p001.json").write_text(
        json.dumps(
            [
                {
                    "number": 62401,
                    "html_url": r1["url"],
                    "title": r1["title"],
                    "body": "",
                    "user": {"login": "a"},
                    "created_at": "2025-01-01T00:00:00Z",
                    "updated_at": r1["updated_at"],
                    "base": {"ref": "main"},
                    "labels": [{"name": "needs-rebase"}],
                    "draft": False,
                }
            ]
        )
    )
    snap_dir = Path("kb")
    build_snapshot(snap_dir, raw_dir=raw, enriched_records=[r1], base_tips={"main": "deadbeef"})
    line = json.loads((snap_dir / "prs.jsonl").read_text().strip())
    assert line["staleness"]["conflicts"] is True
    assert line["staleness"]["files_gone_from_base"] == ["src/old.cc"]
    assert line["precomputed_merge"]["conflicts"] is True
    manifest = json.loads((snap_dir / "manifest.json").read_text())
    assert manifest["base_tips"]["main"] == "deadbeef"

    loaded = load_snapshot(snap_dir)
    findings, _ = query_pr(loaded, 62401, no_tracker=True)
    cats = {f["category"] for f in findings}
    assert "merge-conflict" in cats
    assert "files-gone" in cats


def test_query_uses_precomputed_without_staleness_dict(tmp_path, minimal_pr, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r1 = minimal_pr(72480)
    r1.update(
        {
            "url": "https://github.com/ceph/ceph/pull/72480",
            "updated_at": "2025-06-01T00:00:00Z",
            "precomputed_merge": {"conflicts": True, "conflict_files": ["t.cc"]},
            "git": {
                **r1["git"],
                "conflicts": True,
                "conflict_files": ["t.cc"],
                "files": [{"status": "M", "path": "t.cc", "old_path": "t.cc"}],
            },
        }
    )
    raw = Path("raw")
    raw.mkdir()
    (raw / "pulls_open_p001.json").write_text(
        json.dumps(
            [
                {
                    "number": 72480,
                    "html_url": r1["url"],
                    "title": r1["title"],
                    "body": "",
                    "user": {"login": "a"},
                    "created_at": "2025-01-01T00:00:00Z",
                    "updated_at": r1["updated_at"],
                    "base": {"ref": "main"},
                    "labels": [],
                    "draft": False,
                }
            ]
        )
    )
    snap_dir = Path("kb")
    build_snapshot(snap_dir, raw_dir=raw, enriched_records=[r1])
    loaded = load_snapshot(snap_dir)
    findings, _ = query_pr(loaded, 72480, no_tracker=True)
    assert any(f["category"] == "merge-conflict" for f in findings)


def test_drift_classify_structural_miss():
    from pipeline.drift import classify_miss

    drift = {"structural_drift": True, "base_tip_drift": True}
    assert classify_miss(("merge-conflict", ()), drift, structural_categories=frozenset({"merge-conflict"})) == "drift"
    assert classify_miss(("duplicate", ()), drift, structural_categories=frozenset({"merge-conflict"})) == "drift"
    assert classify_miss(("merge-conflict", ()), {"structural_drift": False}, structural_categories=frozenset({"merge-conflict"})) == "real_miss"
