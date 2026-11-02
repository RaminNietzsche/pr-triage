import subprocess
from datetime import datetime, timezone

from pr_triage.context import get_config
from triage.gitdata import Git
from triage.staleness import staleness


def _git(tmp_path, *args):
    return subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True, text=True)


def test_rename_in_deleting_commit(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    (repo / "requests").mkdir()
    content = "x" * 80 + "\n"
    (repo / "requests" / "sessions.py").write_text(content)
    _git(repo, "add", "requests/sessions.py")
    _git(repo, "commit", "-m", "add sessions")
    merge_base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "checkout", "-b", "pr/99")
    (repo / "requests" / "sessions.py").write_text("pr change\n" + content)
    _git(repo, "commit", "-am", "pr edit")
    pr_head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "update-ref", "refs/pr/99", pr_head)
    _git(repo, "checkout", "main")
    (repo / "src").mkdir()
    (repo / "src" / "requests").mkdir()
    _git(repo, "mv", "requests/sessions.py", "src/requests/sessions.py")
    _git(repo, "commit", "-m", "move to src")
    _git(repo, "update-ref", "refs/remotes/origin/main", _git(repo, "rev-parse", "HEAD").stdout.strip())

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
        },
    }
    row = staleness(git, [rec])[0]
    assert row["files_gone_from_base"] == []
    assert row["files_moved_on_base"]["requests/sessions.py"] == "src/requests/sessions.py"


def test_tiny_rename_pair_stays_files_gone(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    (repo / "tiny.py").write_text("short\n")
    _git(repo, "add", "tiny.py")
    _git(repo, "commit", "-m", "add")
    merge_base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "checkout", "-b", "pr/1")
    (repo / "tiny.py").write_text("pr\n")
    _git(repo, "commit", "-am", "pr")
    pr_head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "update-ref", "refs/pr/1", pr_head)
    _git(repo, "checkout", "main")
    (repo / "dst").mkdir()
    _git(repo, "mv", "tiny.py", "dst/tiny.py")
    _git(repo, "commit", "-m", "mv tiny")
    _git(repo, "update-ref", "refs/remotes/origin/main", _git(repo, "rev-parse", "HEAD").stdout.strip())

    git = Git(str(repo))
    rec = {
        "number": 1,
        "base": "main",
        "updated_at": "2025-01-01T00:00:00Z",
        "labels": [],
        "git": {
            "merge_base": merge_base,
            "files": [{"status": "M", "path": "tiny.py", "old_path": "tiny.py"}],
            "commits_not_in_base": [pr_head],
        },
    }
    row = staleness(git, [rec])[0]
    assert row["files_gone_from_base"] == ["tiny.py"]


def test_symlink_rename_ignored(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    (repo / "pkg").mkdir()
    (repo / "pkg" / "old.py").write_text("x" * 80 + "\n")
    _git(repo, "add", "pkg/old.py")
    _git(repo, "commit", "-m", "add file")
    merge_base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "checkout", "-b", "pr/2")
    (repo / "pkg" / "old.py").write_text("pr edit\n" + "y" * 80)
    _git(repo, "commit", "-am", "pr")
    pr_head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "update-ref", "refs/pr/2", pr_head)
    _git(repo, "checkout", "main")
    (repo / "README.md").write_text("readme\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "readme")
    _git(repo, "rm", "pkg/old.py")
    _git(repo, "commit", "-m", "delete old")
    (repo / "pkg").mkdir(exist_ok=True)
    (repo / "pkg" / "old.py").symlink_to(repo / "README.md")
    _git(repo, "add", "pkg/old.py")
    _git(repo, "commit", "-m", "replace with symlink")
    _git(repo, "mv", "pkg/old.py", "pkg/new.py")
    _git(repo, "commit", "-m", "move symlink")
    _git(repo, "update-ref", "refs/remotes/origin/main", _git(repo, "rev-parse", "HEAD").stdout.strip())

    git = Git(str(repo))
    rec = {
        "number": 2,
        "base": "main",
        "updated_at": "2025-01-01T00:00:00Z",
        "labels": [],
        "git": {
            "merge_base": merge_base,
            "files": [{"status": "M", "path": "pkg/old.py", "old_path": "pkg/old.py"}],
            "commits_not_in_base": [pr_head],
        },
    }
    row = staleness(git, [rec])[0]
    assert row["files_gone_from_base"] == ["pkg/old.py"]


def _setup_relocate_widget(tmp_path, *, extra_added=None, pre_existing_same_basename=None, include_elsewhere=True):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    if pre_existing_same_basename:
        for rel, body in pre_existing_same_basename:
            (repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (repo / rel).write_text(body)
            _git(repo, "add", rel)
        _git(repo, "commit", "-m", "pre existing")
    (repo / "lib").mkdir()
    (repo / "lib" / "widget.py").write_text("ORIGINAL_LIB_WIDGET\n" + "x" * 80 + "\n")
    _git(repo, "add", "lib/widget.py")
    _git(repo, "commit", "-m", "add widget")
    merge_base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "checkout", "-b", "pr/1")
    (repo / "lib" / "widget.py").write_text("PR_EDIT_LIB_WIDGET\n" + "y" * 80 + "\n")
    _git(repo, "commit", "-am", "pr edit")
    pr_head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "update-ref", "refs/pr/1", pr_head)
    _git(repo, "checkout", "main")
    _git(repo, "rm", "lib/widget.py")
    _git(repo, "commit", "-m", "delete widget")
    if include_elsewhere:
        (repo / "elsewhere").mkdir()
        (repo / "elsewhere" / "widget.py").write_text("UNRELATED_ELSEWHERE\n" + "z" * 80 + "\n")
        _git(repo, "add", "elsewhere/widget.py")
    for i, rel in enumerate(extra_added or []):
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(f"UNRELATED_{i}\n" + "q" * 80 + "\n")
        _git(repo, "add", rel)
    if include_elsewhere or extra_added:
        _git(repo, "commit", "-m", "add replacements")
    _git(repo, "update-ref", "refs/remotes/origin/main", _git(repo, "rev-parse", "HEAD").stdout.strip())
    return repo, merge_base, pr_head


def test_basename_one_added_candidate(tmp_path):
    repo, merge_base, pr_head = _setup_relocate_widget(tmp_path)
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


def test_basename_too_many_candidates_stays_gone(tmp_path):
    repo, merge_base, pr_head = _setup_relocate_widget(
        tmp_path,
        include_elsewhere=False,
        extra_added=["a/widget.py", "b/widget.py", "c/widget.py", "d/widget.py"],
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
    assert row["files_gone_from_base"] == ["lib/widget.py"]


def test_basename_preexisting_not_added_ignored(tmp_path):
    repo, merge_base, pr_head = _setup_relocate_widget(
        tmp_path,
        pre_existing_same_basename=[("other/widget.py", "old\n" + "p" * 80)],
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
    assert row["files_probably_moved_on_base"].get("lib/widget.py") == ["elsewhere/widget.py"]


def test_basename_fallback_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(get_config().thresholds, "basename_move_fallback", False)
    repo, merge_base, pr_head = _setup_relocate_widget(tmp_path)
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


def test_true_delete_stays_files_gone(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    (repo / "gone.py").write_text("x" * 80 + "\n")
    _git(repo, "add", "gone.py")
    _git(repo, "commit", "-m", "add")
    merge_base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "checkout", "-b", "pr/7")
    (repo / "gone.py").write_text("pr\n")
    _git(repo, "commit", "-am", "pr touch")
    pr_head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "update-ref", "refs/pr/7", pr_head)
    _git(repo, "checkout", "main")
    _git(repo, "rm", "gone.py")
    _git(repo, "commit", "-m", "remove")
    _git(repo, "update-ref", "refs/remotes/origin/main", _git(repo, "rev-parse", "HEAD").stdout.strip())

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
