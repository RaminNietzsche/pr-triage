# Per-PR pipeline architecture (target-repo CI)

This document describes how to run **pr-triage** from another repository's GitHub Actions
(for example `ceph/ceph`) when a pull request opens or updates, without running a full
batch scan on every event.

## Problem

A full `batch` run over ~1,800 open PRs needs a large clone, every `refs/pull/N/head`, and
tens of minutes to hours. That is appropriate for **scheduled reports**, not for
`pull_request` on every push.

The **per-PR path** reuses a precomputed **KB snapshot** of all open PRs plus inverted
indexes. Querying one PR takes seconds: candidate narrowing, then embedding (or TF-IDF) only
on that subset.

## Components

| Piece | Role |
|-------|------|
| `batch` / `collect` + `enrich` | Populate `data/prs.json` and optional nightly merge/git fields |
| `build-kb` | Write `data/kb-snapshot/` (or `.tar.gz`): records + `indexes/` + manifest |
| `per-pr` | Load snapshot, refresh target PR git if clone present, emit findings |
| Composite action `.github/actions/pr-triage` | Same commands inside CI (read-only by default) |

## Data flow

```
  [Scheduled job in target repo or fork]
       list-open-PRs (cache) -> clone + fetch PR refs -> collect -> build-kb
       -> upload artifact: kb-snapshot.tar.gz

  [pull_request job]
       download kb artifact
       checkout tool (pr-triage) + restore clone cache
       per-pr --pr N --kb ... [--refresh-target] [--json | --render]
       -> Step Summary / artifact / optional PR comment (separate step)
```

## KB snapshot contents

See `kb/schema.py`. Indexes power **similar / overlapping PR** detection:

- **file** – paths touched in the PR effective diff
- **patch_id** / **eff_patch** – stable patch identity
- **ticket** – tracker ids parsed from title/body/commits

`query_pr` (`pipeline/query.py`) gathers `candidates_for(target, indexes)`, embeds
target text + each candidate, and `classify` in `triage/dupes.py` produces pair findings.

## Finding categories relevant to "similar PRs"

| Category | Typical confidence in output | Meaning |
|----------|------------------------------|---------|
| `duplicate` | high / medium | Identical effective patch, commit set, or strong title+file overlap |
| `duplicate-backport` | high | Same cherry-picked main commits |
| `competing-fix` | medium (filtered by default) | Same ticket, different authors, overlapping files |
| `possible-overlap` | low (filtered by default) | Text similarity + hunk overlap |
| `stacked` / `shares-commits` / `related-series` | informational | Structural relations from batch logic; in per-PR context mainly via pairs/clusters |

**Default maintainer filter** (`pipeline/filter.py`, used unless `--all-findings`):

- Includes high-confidence `duplicate`, many `merge-conflict` / `files-gone`, etc.
- **Excludes** most `competing-fix` and `possible-overlap` rows.

For a CI dashboard that lists *all* structurally similar PRs, use:

```bash
python3 -m pr_triage per-pr --config configs/ceph.yml --pr "$PR" --kb data/kb-snapshot --json --all-findings
```

## JSON shape (per-PR)

With `--json`, stdout is one object:

```json
{
  "pr": 71234,
  "meta": {
    "latency_s": 2.1,
    "n_candidates": 48,
    "snapshot_at": "2026-11-03T12:00:00+00:00",
    "enriched": true
  },
  "findings": [ ... filtered high-precision rows ... ],
  "all_findings_count": 12
}
```

Each finding:

```json
{
  "category": "duplicate",
  "confidence": "high",
  "prs": [71234, 70999],
  "reason": "...",
  "score": 1.0,
  "component": "rgw"
}
```

**Similar PR numbers** = every value in `prs` except the queried PR, across categories
you care about (`duplicate`, `duplicate-backport`, `competing-fix`, `possible-overlap`).

Example `jq` (all pair categories, including filtered-out ones, requires `--all-findings`
in the command that produced the JSON file):

```bash
jq -r --argjson n "$PR" '
  .findings[]
  | select(.category | test("^(duplicate|competing-fix|possible-overlap)"))
  | .prs[]
  | select(. != $n)
' "triage-pr-${PR}.json" | sort -u
```

## Fresh PR not in the snapshot

`query_pr` raises if `pr_number` is missing from KB records. Mitigations:

1. **Frequent KB rebuild** (daily cron) so new PRs appear after the next artifact.
2. **On-demand refresh** in the per-PR job: `batch --list-only --refresh`, fetch only
   `refs/pull/$PR/head`, re-run `build-kb` merging existing snapshot (heavier, minutes).
3. **Fail open**: post a short Summary saying "PR not in snapshot yet; retry after nightly build."

## Permissions (GitHub)

| Mode | `permissions` |
|------|----------------|
| Report only (Summary + artifact) | `contents: read` |
| Post/update PR comment | add `pull-requests: write` + a step using `gh` or `github-script` |
| No merge blocking | do not use required checks until precision is agreed |

The bundled composite action does **not** post comments; `post_comment` input is a reminder only.

## Hosting the tool in CI

The target repo workflow typically:

1. Checks out **itself** (for `GITHUB_TOKEN` on the same repo).
2. Checks out **pr-triage** at a pinned tag (second `actions/checkout` with `repository:`).
3. Runs composite action or shell with `working-directory` / `CONFIG=path/to/ceph.yml`.

Configs in pr-triage (`configs/ceph.yml`) point `github.repo` and `clone_dir` at **ceph/ceph**;
in CI, clone paths should match those paths under the workspace root.

## Artifact handoff between workflows

GitHub Actions artifacts from workflow A are **not** automatically visible in workflow B
on the next `pull_request`. Common patterns:

1. **`workflow_run`** – per-PR job triggered after KB workflow completes; download artifact by `run_id`.
2. **`gh run download`** – store `run-id` in repo variable or always fetch latest successful KB run.
3. **Single fork job** – for pilots, run `build-kb` then `per-pr` in one `workflow_dispatch` job.
4. **S3 / release asset** – upload `kb-snapshot.tar.gz` from cron; per-PR job fetches URL.

## Reusable workflows (in pr-triage)

| Workflow | Purpose |
|----------|---------|
| `.github/workflows/reusable-build-kb.yml` | Callable: build + upload `kb-snapshot.tar.gz` |
| `.github/workflows/reusable-query-pr.yml` | Callable: download latest KB, `per-pr`, Job Summary |

Fork setup (two files under `.github/workflows/`):

- `docs/examples/ceph-fork-pr-triage-kb.yml.sample`
- `docs/examples/ceph-fork-pr-triage-on-pr.yml.sample`

Optional `workflow_run` smoke test: `docs/examples/pr-triage-kb-smoke.workflow-run.yml.sample`

Helper scripts: `scripts/ci_download_kb_artifact.sh`, `scripts/ci_write_pr_summary.py`

## Sample workflows (inline / legacy)

- `docs/examples/kb-build.workflow.yml.sample` – full inline KB job
- `docs/examples/per-pr-triage.workflow.yml.sample` – inline per-PR job using `ci_download_kb_artifact.sh`

These files are **not enabled** in pr-triage or upstream; copy into a fork and adjust.
