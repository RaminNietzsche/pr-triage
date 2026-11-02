#!/usr/bin/env python3
"""Legacy entrypoint: prefer `python -m pr_triage batch --config configs/ceph.yml`."""
import argparse
import sys

from pr_triage.batch import run_batch
from pr_triage.context import activate_config


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None, help="Triage profile (default: .pr-triage.yml → configs/ceph.yml)")
    ap.add_argument("--repo", default=None, help="Deprecated; set github.repo in config")
    ap.add_argument("--component", default="all")
    ap.add_argument("--path-prefix", default=None)
    ap.add_argument("--clone", default=None, help="Deprecated; set github.clone_dir in config")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--no-tracker", action="store_true")
    ap.add_argument("--list-only", action="store_true")
    a = ap.parse_args()
    cfg = activate_config(a.config)
    if a.repo and a.repo != cfg.github.repo:
        cfg.github.repo = a.repo
    if a.clone:
        cfg.github.clone_dir = a.clone
    result = run_batch(
        cfg,
        component=a.component,
        path_prefix=a.path_prefix,
        refresh=a.refresh,
        no_tracker=a.no_tracker,
        list_only=a.list_only,
    )
    if result.get("list_only"):
        print(f"{result['total_open']} open PRs cached under data/raw/")
        return
    print(f"{result['analysed']} PRs, {result['findings']} findings -> {result['report_md']}")


if __name__ == "__main__":
    main()
