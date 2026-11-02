from triage.github_ticket import assess_github_closure, partial_fix_vs_pr


def test_assess_drops_stale_sweep():
    issue = {
        "subject": "timeout default",
        "body": "Closing as stale after 90 days of inactivity",
        "state_reason": "completed",
        "merged_fix_prs": [],
        "closing_comments": [],
    }
    out = assess_github_closure(issue, other_issue_open=lambda _n: False)
    assert out["emit"] is False


def test_assess_close_in_favor_open_issue():
    issue = {
        "subject": "x",
        "body": "Closing in favor of #3829",
        "state_reason": "completed",
        "merged_fix_prs": [],
        "closing_comments": [],
    }
    out = assess_github_closure(issue, other_issue_open=lambda n: n == 3829)
    assert out["emit"] is False


def test_partial_fix_when_extra_files():
    merged = [{"number": 6994, "files": ["src/requests/sessions.py"]}]
    pr_files = {"src/requests/sessions.py", "src/requests/adapters.py"}
    pf = partial_fix_vs_pr(merged, pr_files)
    assert pf["category"] == "ticket-partly-superseded"
    assert "adapters.py" in pf["extra"][0]
