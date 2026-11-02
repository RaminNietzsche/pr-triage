"""Render updatable PR comment / check-run markdown (local only, no GitHub POST)."""

MARKER_PREFIX = "<!-- ceph-pr-triage:v1"
MARKER_SUFFIX = "-->"


def marker_comment_id(pr_number: int) -> str:
    return f"ceph-pr-triage-pr-{pr_number}"


def wrap_with_marker(body: str, pr_number: int) -> str:
    mid = marker_comment_id(pr_number)
    return f"{MARKER_PREFIX} id={mid} {MARKER_SUFFIX}\n{body.rstrip()}\n"


def extract_marker_id(text: str) -> str | None:
    for line in text.splitlines()[:5]:
        if line.strip().startswith(MARKER_PREFIX) and "id=" in line:
            part = line.split("id=", 1)[1]
            return part.split(MARKER_SUFFIX, 1)[0].strip()
    return None


def dedupe_key(finding: dict) -> tuple:
    return (finding["category"], tuple(sorted(finding["prs"])), finding.get("confidence"))


def merge_findings(previous_findings: list[dict], new_findings: list[dict]) -> list[dict]:
    """Stable merge for re-runs: keep order, update reason/confidence on same key."""
    prev = {dedupe_key(f): f for f in previous_findings}
    out = []
    seen = set()
    for f in new_findings:
        k = dedupe_key(f)
        seen.add(k)
        out.append({**prev.get(k, {}), **f})
    for k, f in prev.items():
        if k not in seen:
            out.append(f)
    return out


def render_comment(pr_number: int, findings: list[dict], by_number: dict, *, snapshot_at: str, latency_s: float):
    lines = [
        "### Ceph PR triage (read-only assistant)",
        "",
        f"Snapshot `{snapshot_at[:10]}` · queried in **{latency_s:.1f}s** · nothing was posted automatically.",
        "",
    ]
    if not findings:
        lines += ["No high-confidence triage signals for this PR.", ""]
    else:
        lines.append("| Signal | Confidence | Details |")
        lines.append("|---|---|---|")
        for f in findings:
            prs = " ".join(f"#{n}" for n in f["prs"])
            if len(f["prs"]) == 1:
                title = by_number.get(f["prs"][0], {}).get("title", "")[:50]
                prs += f" - {title}"
            reason = f["reason"].replace("|", "/").replace("\n", " ")[:240]
            lines.append(f"| **{f['category']}** | {f['confidence']} | {prs}: {reason} |")
        lines.append("")
    lines.append(
        "_Findings are candidates for human review, not merge blockers. "
        "Re-runs update this comment in place when the workflow uses the hidden marker id._"
    )
    return wrap_with_marker("\n".join(lines), pr_number)
