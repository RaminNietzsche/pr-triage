from pipeline.comment import (
    dedupe_key,
    extract_marker_id,
    merge_findings,
    render_comment,
    wrap_with_marker,
)


def test_marker_roundtrip():
    body = wrap_with_marker("hello", 42)
    assert extract_marker_id(body) == "ceph-pr-triage-pr-42"
    assert "hello" in body


def test_merge_findings_updates_reason():
    prev = [{"category": "merge-conflict", "prs": [1], "confidence": "high", "reason": "old"}]
    new = [{"category": "merge-conflict", "prs": [1], "confidence": "high", "reason": "new"}]
    merged = merge_findings(prev, new)
    assert len(merged) == 1
    assert merged[0]["reason"] == "new"


def test_dedupe_key_stable():
    a = {"category": "duplicate", "prs": [2, 1], "confidence": "high"}
    b = {"category": "duplicate", "prs": [1, 2], "confidence": "high"}
    assert dedupe_key(a) == dedupe_key(b)


def test_render_comment_table():
    by = {9: {"title": "fix foo"}}
    md = render_comment(9, [{"category": "merge-conflict", "prs": [9], "confidence": "high", "reason": "conflict in a.cc"}], by, snapshot_at="2025-01-01T00:00:00Z", latency_s=1.2)
    assert "merge-conflict" in md
    assert "ceph-pr-triage:v1" in md
