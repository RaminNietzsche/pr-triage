from triage.tracker import primary_tickets, tickets


def test_tickets_finds_all_urls():
    text = "See https://tracker.ceph.com/issues/12345 and tracker.ceph.com/issues/9999"
    assert tickets(text) == ["9999", "12345"]


def test_primary_fixes_line():
    body = "Fixes: https://tracker.ceph.com/issues/80894"
    assert primary_tickets(body) == ["80894"]


def test_primary_resolves_case_insensitive():
    assert primary_tickets("RESOLVES: https://tracker.ceph.com/issues/10001") == ["10001"]


def test_bare_url_whole_line_only():
    assert primary_tickets("https://tracker.ceph.com/issues/68808") == ["68808"]
    wrapped = "https://tracker.ceph.com/issues/68808) if the peer fails"
    assert primary_tickets(wrapped) == []


def test_bare_url_with_trailing_punctuation():
    assert primary_tickets("  https://tracker.ceph.com/issues/4242;  ") == ["4242"]


def test_context_url_not_primary():
    body = "Validates the fix for https://tracker.ceph.com/issues/77564 in tests"
    assert primary_tickets(body) == []
    assert "77564" in tickets(body)


def test_related_to_line_not_primary():
    assert primary_tickets("Related to https://tracker.ceph.com/issues/12345") == []


def test_fixes_in_commit_message():
    msg = "osd: fix crash\n\nFixes: https://tracker.ceph.com/issues/80894"
    assert primary_tickets(msg) == ["80894"]


def test_primary_ticket_texts_uses_both_commit_fields():
    from triage.tracker import primary_ticket_texts

    rec = {"title": "", "body": "", "git": {"new_commit_msgs": "", "commit_msgs": "Fixes: https://tracker.ceph.com/issues/4242"}}
    assert primary_tickets(*primary_ticket_texts(rec)) == ["4242"]
