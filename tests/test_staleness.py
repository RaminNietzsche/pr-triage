import subprocess
from datetime import datetime, timezone

from triage.gitdata import Git
from triage.staleness import staleness


def _git(tmp_path, *args):
    return subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True, text=True)


def test_rename_into_src_not_files_gone(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    (repo / "requests").mkdir()
    (repo / "requests" / "sessions.py").write_text("v1\n")
    _git(repo, "add", "requests/sessions.py")
    _git(repo, "commit", "-m", "add sessions")
    merge_base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "checkout", "-b", "pr/99")
    (repo / "requests" / "sessions.py").write_text("pr change\n")
    _git(repo, "commit", "-am", "pr edit")
    pr_head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "update-ref", "refs/pr/99", pr_head)
    _git(repo, "checkout", "main")
    (repo / "src").mkdir()
    (repo / "src" / "requests").mkdir()
    _git(repo, "mv", "requests/sessions.py", "src/requests/sessions.py")
    _git(repo, "commit", "-m", "move to src")
    tip = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "update-ref", "refs/remotes/origin/main", tip)

    git = Git(str(repo))
    rec = {
        "number": 99,
        "base": "main",
        "updated_at": "2025-01-01T00:00:00Z",
        "labels": [],
        "git": {
            "merge_base": merge_base,
            "files": [{"status": "M", "path": "requests/sessions.py", "old_path": "requests/sessions.py"}],
            "commits_not_in_base": [pr_head],
            "conflicts": True,
            "conflict_files": ["src/requests/sessions.py"],
        },
    }
    rows = staleness(git, [rec], now=datetime(2025, 6, 1, tzinfo=timezone.utc))
    assert len(rows) == 1
    row = rows[0]
    assert row["files_gone_from_base"] == []
    assert row["files_moved_on_base"]["requests/sessions.py"] == "src/requests/sessions.py"


def test_true_delete_stays_files_gone(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    (repo / "gone.py").write_text("x\n")
    _git(repo, "add", "gone.py")
    _git(repo, "commit", "-m", "add")
    merge_base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / "gone.py").write_text("pr\n")
    _git(repo, "commit", "-am", "pr touch")
    pr_head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "update-ref", "refs/pr/7", pr_head)
    _git(repo, "rm", "gone.py")
    _git(repo, "commit", "-m", "remove")
    tip = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "update-ref", "refs/remotes/origin/main", tip)

    git = Git(str(repo))
    rec = {
        "number": 7,
        "base": "main",
        "updated_at": "2025-01-01T00:00:00Z",
        "labels": [],
        "git": {
            "merge_base": merge_base,
            "files": [{"status": "M", "path": "gone.py", "old_path": "gone.py"}],
            "commits_not_in_base": [pr_head],
        },
    }
    row = staleness(git, [rec], now=datetime(2025, 6, 1, tzinfo=timezone.utc))[0]
    assert row["files_gone_from_base"] == ["gone.py"]
