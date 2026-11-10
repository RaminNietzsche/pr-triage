from pipeline.comment import extract_marker_id
from pipeline.pr_comment_body import render_not_in_snapshot_comment, render_similar_pr_comment


def test_render_similar_includes_marker():
    data = {
        "meta": {"snapshot_at": "2026-01-01T00:00:00Z", "latency_s": 1.0},
        "findings": [
            {
                "category": "duplicate",
                "confidence": "high",
                "prs": [9, 8],
                "reason": "identical effective patch",
            }
        ],
    }
    md = render_similar_pr_comment(9, data)
    assert extract_marker_id(md) == "ceph-pr-triage-pr-9"
    assert "duplicate" in md
    assert "ceph/ceph/pull/8" in md


def test_render_not_in_snapshot():
    md = render_not_in_snapshot_comment(5, query_pr=70000)
    assert extract_marker_id(md) == "ceph-pr-triage-pr-5"
    assert "70000" in md
