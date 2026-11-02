#!/usr/bin/env python3
"""Per-PR triage against a KB snapshot (no full batch re-scan).

Usage:
  python per_pr.py --pr 71234 --kb data/kb-snapshot
  python per_pr.py --pr 71234 --kb data/kb-snapshot.tar.gz --render
"""
import argparse
import json
import sys
from pathlib import Path

from kb.load import load_snapshot
from pipeline.comment import render_comment
from pipeline.filter import filter_findings
from pipeline.query import query_pr


def main():
    ap = argparse.ArgumentParser(description="Query ceph PR triage KB for one PR")
    ap.add_argument("--pr", type=int, required=True)
    ap.add_argument("--kb", default="data/kb-snapshot", help="snapshot dir or .tar.gz")
    ap.add_argument("--clone", default="data/repo/ceph", help="optional git clone for fresh git signals")
    ap.add_argument(
        "--refresh-target",
        action="store_true",
        help="re-run git merge-tree / staleness for this PR only against current base tip (uses --clone)",
    )
    ap.add_argument("--no-tracker", action="store_true")
    ap.add_argument("--all-findings", action="store_true", help="include low/medium informational categories")
    ap.add_argument("--render", action="store_true", help="print markdown comment body")
    ap.add_argument("--json", action="store_true", help="print JSON findings")
    args = ap.parse_args()

    snap = load_snapshot(Path(args.kb))
    use_clone = args.refresh_target or Path(args.clone).is_dir()
    clone_path = args.clone if use_clone and Path(args.clone).is_dir() else None
    if args.refresh_target and not clone_path:
        print(f"warning: --refresh-target ignored (missing clone at {args.clone})", file=sys.stderr)
    findings, meta = query_pr(
        snap,
        args.pr,
        clone=clone_path,
        no_tracker=args.no_tracker,
    )
    shown = filter_findings(findings, all_findings=args.all_findings)
    by_n = {r["number"]: r for r in snap["records"]}

    if args.render:
        print(render_comment(args.pr, shown, by_n, snapshot_at=meta.get("snapshot_at") or "", latency_s=meta["latency_s"]))
    elif args.json:
        print(json.dumps({"pr": args.pr, "meta": meta, "findings": shown, "all_findings_count": len(findings)}, indent=2))
    else:
        print(f"PR #{args.pr}: {len(shown)} high-precision findings ({len(findings)} total) in {meta['latency_s']:.2f}s")
        for f in shown:
            print(f"  [{f['confidence']}] {f['category']}: {f['reason'][:120]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
