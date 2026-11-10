#!/usr/bin/env python3
"""Render GitHub Actions Job Summary markdown from per-pr JSON output."""

import json
import sys

from pipeline.pr_comment_body import SIMILAR_CATEGORIES, STRUCTURAL_CATEGORIES
from pr_triage.safepath import SafePath, allowed_base


def render_summary(pr_number: int, data: dict) -> str:
    lines = [
        "### PR triage (read-only)",
        "",
        f"Queried PR **#{pr_number}** against KB snapshot. Not a merge gate.",
        "",
    ]
    meta = data.get("meta") or {}
    snap = meta.get("snapshot_at") or "?"
    lines += [
        f"- Candidates indexed: **{meta.get('n_candidates', '?')}**",
        f"- Snapshot: `{str(snap)[:19]}`",
        f"- Latency: **{float(meta.get('latency_s', 0)):.1f}s**",
        "",
    ]
    findings = data.get("findings") or []
    similar = [
        f
        for f in findings
        if f.get("category") in SIMILAR_CATEGORIES or "duplicate" in (f.get("category") or "")
    ]
    if not similar:
        lines.append("No duplicate/overlap findings in output.")
        lines.append("")
    else:
        lines += ["| Category | Confidence | Other PR(s) | Note |", "|---|---|---|---|"]
        for f in similar:
            others = [p for p in f["prs"] if p != pr_number]
            note = (f.get("reason") or "").replace("|", "/")[:120]
            other_s = ", ".join(f"#{x}" for x in others)
            lines.append(f"| {f['category']} | {f['confidence']} | {other_s} | {note} |")
        lines.append("")
    struct = [f for f in findings if f.get("category") in STRUCTURAL_CATEGORIES]
    if struct:
        lines += ["**Structural / tracker signals**", "", "| Category | Confidence | Details |", "|---|---|---|"]
        for f in struct[:10]:
            note = (f.get("reason") or "").replace("|", "/")[:100]
            lines.append(f"| {f['category']} | {f['confidence']} | {note} |")
        lines.append("")
    return "\n".join(lines)


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 2:
        print("usage: ci_write_pr_summary.py PR_NUMBER json_path", file=sys.stderr)
        return 2
    pr_number = int(argv[0])
    data = json.loads(SafePath(argv[1], allowed_base()).read_text())
    sys.stdout.write(render_summary(pr_number, data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
