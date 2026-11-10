#!/usr/bin/env python3
"""Create or update a PR issue comment identified by the ceph-pr-triage HTML marker."""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

from pipeline.comment import extract_marker_id, marker_comment_id

API = "https://api.github.com"


def _request(method: str, url: str, payload: dict | None = None):
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        print("GITHUB_TOKEN or GH_TOKEN required", file=sys.stderr)
        return None, 401
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "pr-triage (comment upsert)",
        "Authorization": f"Bearer {token}",
    }
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read().decode()
            return (json.loads(body) if body else {}), r.status
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        print(f"{method} {url} -> {e.code}: {err[:500]}", file=sys.stderr)
        return None, e.code


def list_issue_comments(repo: str, issue_number: int) -> list:
    out = []
    page = 1
    while True:
        url = f"{API}/repos/{repo}/issues/{issue_number}/comments?per_page=100&page={page}"
        data, code = _request("GET", url)
        if code != 200 or data is None:
            break
        out.extend(data)
        if len(data) < 100:
            break
        page += 1
    return out


def upsert_comment(repo: str, issue_number: int, body: str) -> int:
    want_id = marker_comment_id(issue_number)
    existing_id = None
    for c in list_issue_comments(repo, issue_number):
        if extract_marker_id(c.get("body") or "") == want_id:
            existing_id = c["id"]
            break
    if existing_id is not None:
        url = f"{API}/repos/{repo}/issues/comments/{existing_id}"
        _, code = _request("PATCH", url, {"body": body})
        if code != 200:
            return 1
        print(f"updated comment {existing_id} on {repo}#{issue_number}")
        return 0
    url = f"{API}/repos/{repo}/issues/{issue_number}/comments"
    _, code = _request("POST", url, {"body": body})
    if code != 201:
        return 1
    print(f"created comment on {repo}#{issue_number}")
    return 0


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    ap = argparse.ArgumentParser(description="Upsert ceph-pr-triage PR comment")
    ap.add_argument("--repo", required=True, help="owner/name where the PR lives")
    ap.add_argument("--pr", type=int, required=True, help="PR number (issue number)")
    ap.add_argument("--body-file", required=True, help="Markdown file (may include marker)")
    args = ap.parse_args(argv)
    body = open(args.body_file, encoding="utf-8").read()
    return upsert_comment(args.repo, args.pr, body)


if __name__ == "__main__":
    raise SystemExit(main())
