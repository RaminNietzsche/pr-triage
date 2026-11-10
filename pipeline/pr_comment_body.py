"""Markdown bodies for maintainer-facing PR comments (similar PRs + optional structural)."""

from pipeline.comment import wrap_with_marker

SIMILAR_CATEGORIES = frozenset(
    {
        "duplicate",
        "duplicate-backport",
        "competing-fix",
        "possible-overlap",
        "stacked",
        "shares-commits",
        "related-series",
        "stated-supersede",
    }
)
STRUCTURAL_CATEGORIES = frozenset(
    {
        "merge-conflict",
        "files-gone",
        "files-moved-on-base",
        "already-in-base",
        "ticket-closed",
    }
)


def _pr_link(repo: str, n: int) -> str:
    return f"https://github.com/{repo}/pull/{n}"


def render_similar_pr_comment(
    pr_number: int,
    data: dict,
    *,
    github_repo: str = "ceph/ceph",
    include_structural: bool = True,
    max_similar_rows: int = 30,
    max_structural_rows: int = 8,
) -> str:
    meta = data.get("meta") or {}
    snap = str(meta.get("snapshot_at") or "?")[:19]
    latency = float(meta.get("latency_s", 0))
    findings = data.get("findings") or []

    lines = [
        "### Ceph PR triage — related open PRs",
        "",
        f"Queried **#{pr_number}** against KB snapshot `{snap}` in **{latency:.1f}s**.",
        "Signals are **candidates for human review**, not merge blockers.",
        "",
    ]

    similar = [
        f
        for f in findings
        if f.get("category") in SIMILAR_CATEGORIES or "duplicate" in (f.get("category") or "")
    ]
    if not similar:
        lines += ["No duplicate, overlap, or series relations in this run.", ""]
    else:
        lines += [
            "| Category | Confidence | Other PR(s) | Note |",
            "|---|---|---|---|",
        ]
        for f in similar[:max_similar_rows]:
            others = [p for p in f["prs"] if p != pr_number]
            note = (f.get("reason") or "").replace("|", "/").replace("\n", " ")[:160]
            other_cells = ", ".join(f"[#{x}]({_pr_link(github_repo, x)})" for x in others)
            lines.append(f"| **{f['category']}** | {f['confidence']} | {other_cells or '—'} | {note} |")
        if len(similar) > max_similar_rows:
            lines.append("")
            lines.append(f"_… and {len(similar) - max_similar_rows} more rows (see workflow artifact)._")
        lines.append("")

    if include_structural:
        struct = [f for f in findings if f.get("category") in STRUCTURAL_CATEGORIES]
        if struct:
            lines += ["**Other high-signal checks**", "", "| Category | Confidence | Details |", "|---|---|---|"]
            for f in struct[:max_structural_rows]:
                note = (f.get("reason") or "").replace("|", "/").replace("\n", " ")[:120]
                related = [p for p in f.get("prs", []) if p != pr_number]
                extra = ""
                if related:
                    extra = " " + ", ".join(f"[#{x}]({_pr_link(github_repo, x)})" for x in related[:5])
                lines.append(f"| {f['category']} | {f['confidence']} | {note}{extra} |")
            lines.append("")

    lines.append(
        "_This comment is updated in place when the workflow re-runs (hidden HTML marker). "
        "Data: read-only GitHub + local git analysis; no labels or merges were changed._"
    )
    return wrap_with_marker("\n".join(lines), pr_number)


def render_not_in_snapshot_comment(pr_number: int, *, query_pr: int | None = None) -> str:
    q = query_pr if query_pr is not None else pr_number
    body = "\n".join(
        [
            "### Ceph PR triage",
            "",
            f"PR **#{q}** is not in the latest KB snapshot yet (or the query failed).",
            "After the nightly KB workflow succeeds, push a new commit or re-run the workflow.",
            "",
            "_Read-only assistant; not a merge gate._",
        ]
    )
    return wrap_with_marker(body, pr_number)
