import json
from pathlib import Path

from kb.build import build_snapshot
from kb.indexes import build_indexes, candidates_for
from kb.load import load_snapshot
from pipeline.query import query_pr


def test_build_and_query_minimal_kb(tmp_path, minimal_pr):
    r1 = minimal_pr(1, patch_ids=["pid-a"], eff_patch_id="ep-a")
    r1.update({"url": "https://github.com/ceph/ceph/pull/1", "enriched": True, "updated_at": "2025-01-01T00:00:00Z"})
    r2 = minimal_pr(2, patch_ids=["pid-a"], eff_patch_id="ep-a")
    r2.update({"url": "https://github.com/ceph/ceph/pull/2", "enriched": True, "updated_at": "2025-01-01T00:00:00Z"})
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "pulls_open_p001.json").write_text(
        json.dumps(
            [
                {"number": 1, "html_url": r1["url"], "title": r1["title"], "body": "", "user": {"login": "a"},
                 "created_at": "2025-01-01T00:00:00Z", "updated_at": r1["updated_at"],
                 "base": {"ref": "main"}, "labels": [], "draft": False},
                {"number": 2, "html_url": r2["url"], "title": r2["title"], "body": "", "user": {"login": "b"},
                 "created_at": "2025-01-01T00:00:00Z", "updated_at": r2["updated_at"],
                 "base": {"ref": "main"}, "labels": [], "draft": False},
            ]
        )
    )
    snap_dir = tmp_path / "kb"
    build_snapshot(snap_dir, raw_dir=raw, enriched_records=[r1, r2])
    loaded = load_snapshot(snap_dir)
    assert loaded["manifest"]["n_open"] == 2
    idx = loaded["indexes"]
    assert "pid-a" in idx["patch_id"]
    by_n = {r["number"]: r for r in loaded["records"]}
    assert candidates_for(r1, idx, by_n) == [2]
    findings, meta = query_pr(loaded, 1, no_tracker=True)
    cats = [f["category"] for f in findings]
    assert "duplicate" in cats
    assert meta["latency_s"] >= 0
