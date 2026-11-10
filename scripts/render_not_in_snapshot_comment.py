#!/usr/bin/env python3
"""Stdout: marker-wrapped comment when per-pr query failed."""

import argparse
import sys

from pipeline.pr_comment_body import render_not_in_snapshot_comment


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--comment-pr", type=int, required=True)
    ap.add_argument("--query-pr", type=int, required=True)
    args = ap.parse_args()
    sys.stdout.write(render_not_in_snapshot_comment(args.comment_pr, query_pr=args.query_pr))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
