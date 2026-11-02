"""Unified CLI: build-kb, batch, per-pr."""

import argparse
import json
import sys
from pathlib import Path

from pr_triage.batch import run_batch
from pr_triage.context import activate_config
from pr_triage.safepath import allowed_base, resolve_under


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--config", "-c", default=None, help="Path to configs/<profile>.yml")
    ap = argparse.ArgumentParser(prog="pr-triage", description="Config-driven read-only PR triage")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_batch = sub.add_parser("batch", parents=[shared], help="Full batch triage report")
    p_batch.add_argument("--component", default="all")
    p_batch.add_argument("--path-prefix", default=None)
    p_batch.add_argument("--refresh", action="store_true")
    p_batch.add_argument("--no-tracker", action="store_true")
    p_batch.add_argument("--list-only", action="store_true")

    p_kb = sub.add_parser("build-kb", parents=[shared], help="Build KB snapshot from cached PR data")
    p_kb.add_argument("--out", default="data/kb-snapshot")
    p_kb.add_argument("--raw", default=None)
    p_kb.add_argument("--prs-cache", default=None)

    p_pr = sub.add_parser("per-pr", parents=[shared], help="Query one PR against a KB snapshot")
    p_pr.add_argument("--pr", type=int, required=True)
    p_pr.add_argument("--kb", default="data/kb-snapshot")
    p_pr.add_argument("--clone", default=None)
    p_pr.add_argument("--refresh-target", action="store_true")
    p_pr.add_argument("--no-tracker", action="store_true")
    p_pr.add_argument("--all-findings", action="store_true")
    p_pr.add_argument("--render", action="store_true")
    p_pr.add_argument("--json", action="store_true")

    args = ap.parse_args(argv)
    cfg = activate_config(args.config)

    if args.cmd == "batch":
        result = run_batch(
            cfg,
            component=args.component,
            path_prefix=args.path_prefix,
            refresh=args.refresh,
            no_tracker=args.no_tracker,
            list_only=args.list_only,
        )
        if result.get("list_only"):
            print(f"{result['total_open']} open PRs cached")
            return 0
        print(
            f"{result['analysed']} PRs, {result['findings']} findings "
            f"({result['actionable_prs']} actionable PRs, "
            f"{result['actionable_high_findings']} high) -> {result['report_md']}"
        )
        return 0

    if args.cmd == "build-kb":
        from kb.build import build_snapshot
        from kb.enrich import enrich_prs

        root = allowed_base()
        raw = resolve_under(args.raw or cfg.paths.raw_dir, root)
        prs_cache = resolve_under(args.prs_cache or cfg.paths.prs_cache, root)
        clone = cfg.github.clone_dir
        enriched = enrich_prs(raw, clone) if Path(clone).is_dir() else None
        build_snapshot(
            resolve_under(args.out, root),
            repo=cfg.github.repo,
            raw_dir=raw,
            prs_cache=prs_cache,
            enriched_records=enriched,
        )
        print(f"KB snapshot -> {args.out}")
        return 0

    if args.cmd == "per-pr":
        from kb.load import load_snapshot
        from pipeline.comment import render_comment
        from pipeline.filter import filter_findings
        from pipeline.query import query_pr

        clone = args.clone or cfg.github.clone_dir
        snap = load_snapshot(resolve_under(args.kb, allowed_base()))
        use_clone = args.refresh_target or Path(clone).is_dir()
        clone_path = clone if use_clone and Path(clone).is_dir() else None
        if args.refresh_target and not clone_path:
            print(f"warning: --refresh-target ignored (missing clone at {clone})", file=sys.stderr)
        findings, meta = query_pr(snap, args.pr, clone=clone_path, no_tracker=args.no_tracker)
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
    return 1


if __name__ == "__main__":
    sys.exit(main())
