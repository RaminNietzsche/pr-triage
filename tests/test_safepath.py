import tarfile
from pathlib import Path

import pytest

from pr_triage.safepath import (
    SafePathError,
    allowed_base,
    assert_realpath_under,
    extract_tarball,
    resolve_config_path,
    resolve_under,
)


def test_resolve_under_accepts_relative(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sub = tmp_path / "data" / "raw"
    sub.mkdir(parents=True)
    got = resolve_under("data/raw")
    assert got == sub.resolve()


def test_resolve_under_accepts_nested_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    f = tmp_path / "reports" / "out.csv"
    f.parent.mkdir(parents=True)
    f.write_text("x")
    assert resolve_under("reports/out.csv") == f.resolve()


def test_resolve_under_rejects_traversal(tmp_path, monkeypatch):
    proj = tmp_path / "proj"
    proj.mkdir()
    (tmp_path / "secret.txt").write_text("nope")
    monkeypatch.chdir(proj)
    with pytest.raises(SafePathError):
        resolve_under("../../secret.txt")


def test_resolve_config_path_under_workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "configs" / "app.yml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text("name: x\n")
    assert resolve_config_path("configs/app.yml") == cfg.resolve()


def test_extract_tarball_rejects_dotdot(tmp_path):
    archive = tmp_path / "bad.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        info = tarfile.TarInfo(name="../escape.txt")
        info.size = 0
        tf.addfile(info)
    dest = tmp_path / "dest"
    with tarfile.open(archive, "r:gz") as tf:
        with pytest.raises(SafePathError):
            extract_tarball(tf, dest)


def test_assert_realpath_under_rejects_escape(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "secret.out").write_text("x")
    with pytest.raises(SafePathError):
        assert_realpath_under("../../secret.out")


def test_assert_realpath_under_accepts_relative(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    got = assert_realpath_under("data/out.tar.gz")
    assert got == str((tmp_path / "data" / "out.tar.gz").resolve())


def test_extract_tarball_accepts_normal_member(tmp_path):
    archive = tmp_path / "ok.tar.gz"
    payload = tmp_path / "payload.txt"
    payload.write_text("hello")
    with tarfile.open(archive, "w:gz") as tf:
        tf.add(payload, arcname="snap/payload.txt")
    dest = tmp_path / "dest"
    with tarfile.open(archive, "r:gz") as tf:
        extract_tarball(tf, dest)
    assert (dest / "snap" / "payload.txt").read_text() == "hello"
