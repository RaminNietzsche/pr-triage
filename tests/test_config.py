from pathlib import Path

import pytest

from pr_triage.config import load_config
from pr_triage.context import activate_config


def test_load_ceph_config():
    cfg = load_config("configs/ceph.yml")
    assert cfg.github.repo == "ceph/ceph"
    assert cfg.report.display_name == "Ceph"
    assert cfg.report.tool_name == "ceph-pr-triage"


def test_load_requests_config_report():
    cfg = load_config("configs/requests.yml")
    assert cfg.report.display_name == "Requests"
    assert cfg.report.tool_name == "pr-triage"


def test_load_requests_profile():
    cfg = load_config("configs/requests.yml")
    assert cfg.github.repo == "psf/requests"
    assert cfg.tracker.plugin == "github_issues"
    assert cfg.paths.raw_dir == "data-requests/raw"


def test_dot_pr_triage_default():
    activate_config(None)
    from pr_triage.context import get_config

    assert get_config().name == "ceph"


def test_requests_primary_ticket_parsing():
    activate_config("configs/requests.yml")
    from triage.tracker import primary_tickets, tickets

    body = "Fixes #1234\nSee also https://github.com/psf/requests/issues/999"
    assert primary_tickets(body) == ["1234"]
    assert "999" in tickets(body)
