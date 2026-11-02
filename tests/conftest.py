import pytest

from pr_triage.context import activate_config


@pytest.fixture(autouse=True)
def _default_triage_config():
    activate_config("configs/ceph.yml")


@pytest.fixture
def minimal_pr():
    """Minimal PR record for dupes/classify tests."""

    def _make(
        number,
        base="main",
        author="alice",
        title="fix rgw bug",
        commit_authors=None,
        eff_files=None,
        patch_ids=None,
        cherry=None,
        eff_patch_id=None,
        hunks=None,
        tickets=None,
    ):
        commit_authors = commit_authors or [author.lower()]
        eff_files = eff_files or ["src/rgw/foo.cc"]
        patch_ids = patch_ids or ["p1"]
        cherry = cherry or []
        hunks = hunks or {eff_files[0]: [(1, 10)]}
        tickets = tickets or []
        return {
            "number": number,
            "author": author,
            "base": base,
            "title": title,
            "body": "",
            "new_tickets": tickets,
            "commit_authors": commit_authors,
            "git": {
                "eff_files": eff_files,
                "new_commit_patch_ids": patch_ids,
                "new_cherry_picked_from": cherry,
                "eff_patch_id": eff_patch_id,
                "eff_hunks": hunks,
                "new_commit_msgs": "fix something",
            },
        }

    return _make
