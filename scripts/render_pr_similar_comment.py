#!/usr/bin/env python3
"""Render PR comment markdown from per-pr JSON (--json output)."""

import argparse
import json
import sys

from pipeline.pr_comment_body import render_similar_pr_comment
from pr_triage.safepath import SafePath, allowed_base


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    ap = argparse.ArgumentParser()
    ap.add_argument("pr_number", type=int)
    ap.add_argument("json_path")
    ap.add_argument("--repo", default="ceph/ceph", help="GitHub repo for pull links")
    ap.add_argument("--no-structural", action="store_true")
    args = ap.parse_args(argv)
    data = json.loads(SafePath(args.json_path, allowed_base()).read_text())
    md = render_similar_pr_comment(
        args.pr_number,
        data,
        github_repo=args.repo,
        include_structural=not args.no_structural,
    )
    sys.stdout.write(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
