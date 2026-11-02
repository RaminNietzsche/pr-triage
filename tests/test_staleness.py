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


def _setup_missing_path_repo(tmp_path, *, extra_same_basenames=None):
    """PR touches lib/widget.py; main replaces it with elsewhere/widget.py (no git rename)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    (repo / "lib").mkdir()
    (repo / "lib" / "widget.py").write_text("original\n")
    _git(repo, "add", "lib/widget.py")
    _git(repo, "commit", "-m", "add widget")
    merge_base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "checkout", "-b", "pr/1")
    (repo / "lib" / "widget.py").write_text("pr edit\n")
    _git(repo, "commit", "-am", "pr edit")
    pr_head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "update-ref", "refs/pr/1", pr_head)
    _git(repo, "checkout", "main")
    _git(repo, "rm", "lib/widget.py")
    (repo / "elsewhere").mkdir()
    (repo / "elsewhere" / "widget.py").write_text("totally different content on main\n")
    _git(repo, "add", "elsewhere/widget.py")
    for rel in extra_same_basenames or []:
        parent = repo / rel
        parent.parent.mkdir(parents=True, exist_ok=True)
        parent.write_text("other copy\n")
        _git(repo, "add", rel)
    _git(repo, "commit", "-m", "relocate widget")
    tip = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "update-ref", "refs/remotes/origin/main", tip)
    return repo, merge_base, pr_head


def test_basename_fallback_single_candidate(tmp_path):
    repo, merge_base, pr_head = _setup_missing_path_repo(tmp_path)
    git = Git(str(repo))
    rec = {
        "number": 1,
        "base": "main",
        "updated_at": "2025-01-01T00:00:00Z",
        "labels": [],
        "git": {
            "merge_base": merge_base,
            "files": [{"status": "M", "path": "lib/widget.py", "old_path": "lib/widget.py"}],
            "commits_not_in_base": [pr_head],
        },
    }
    row = staleness(git, [rec])[0]
    assert row["files_gone_from_base"] == []
    assert row["files_probably_moved_on_base"]["lib/widget.py"] == ["elsewhere/widget.py"]


def test_basename_fallback_multiple_candidates(tmp_path):
    repo, merge_base, pr_head = _setup_missing_path_repo(
        tmp_path, extra_same_basenames=["alt/widget.py", "pkg/widget.py"]
    )
    git = Git(str(repo))
    rec = {
        "number": 1,
        "base": "main",
        "updated_at": "2025-01-01T00:00:00Z",
        "labels": [],
        "git": {
            "merge_base": merge_base,
            "files": [{"status": "M", "path": "lib/widget.py", "old_path": "lib/widget.py"}],
            "commits_not_in_base": [pr_head],
        },
    }
    row = staleness(git, [rec])[0]
    assert len(row["files_probably_moved_on_base"]["lib/widget.py"]) == 3


def test_basename_fallback_disabled_stays_files_gone(tmp_path, monkeypatch):
    from pr_triage.context import get_config

    monkeypatch.setattr(get_config().thresholds, "basename_move_fallback", False)
    repo, merge_base, pr_head = _setup_missing_path_repo(tmp_path)
    git = Git(str(repo))
    rec = {
        "number": 1,
        "base": "main",
        "updated_at": "2025-01-01T00:00:00Z",
        "labels": [],
        "git": {
            "merge_base": merge_base,
            "files": [{"status": "M", "path": "lib/widget.py", "old_path": "lib/widget.py"}],
            "commits_not_in_base": [pr_head],
        },
    }
    row = staleness(git, [rec])[0]
    assert row["files_gone_from_base"] == ["lib/widget.py"]
