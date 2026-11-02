# Generic PR triage pipeline - design

## Problem

The original tool hard-coded Ceph-specific paths: `tracker.ceph.com` URL parsing, Redmine status names, component path globs, release-branch names, and default clone locations. That made the core useful only for one repository.

## Approach

Separate **engine** (under `triage/`, `kb/`, `pipeline/`) from **profile** (YAML under `configs/`). The engine reads an active `TriageConfig` via `pr_triage.context` before each run.

### Configuration layers

| File | Role |
|------|------|
| `.pr-triage.yml` | Optional pointer: `config: configs/<profile>.yml` |
| `configs/<profile>.yml` | Full profile: GitHub repo, branches, components, tracker plugin, thresholds |
| `.pr-triage.yml` in a consumer repo | Same schema; can live in the target repo when the action runs |

### Schema (high level)

- **github**: `repo`, `default_base`, `clone_dir`, `release_branches`
- **tracker**: `plugin` (`redmine` | `github_issues` | `jira` | `none`), URL regex, status sets, polite delay
- **components**: ordered `label_priority`, `path_rules` (prefix → component name)
- **labels / thresholds / paths / limits / scopes**: operational tuning
- **limitations_extra**: profile-specific caveats appended to reports

Ceph reference data lives entirely in `configs/ceph.yml` (generated from the former Python tables so the two stay aligned at import time).

### Tracker adapters

`pr_triage/trackers/` implements a small protocol:

- **redmine** : public Redmine JSON (`/issues/N.json`), used for Ceph
- **github_issues** : same-repo GitHub Issues REST API (default for generic repos)
- **jira** : stub returning structured placeholders until site credentials exist
- **none** : skip ticket status lookups

Ticket *parsing* remains in `triage/tracker.py` but uses the configured `issue_id_regex` and GitHub-style `Fixes #N` when the plugin is `github_issues`.

### CLI

`python -m pr_triage` subcommands:

- `batch --config …` : full report (replaces most of `run.py`)
- `build-kb --config …` : nightly KB snapshot
- `per-pr --config …` : single-PR query against a snapshot

Legacy `run.py` and `./triage.sh` remain; they activate the default Ceph profile.

### GitHub Actions

Composite action `.github/actions/pr-triage` runs list → clone/fetch → batch or KB build with **contents: read** only. Sample workflows under `docs/examples/*.sample` are not enabled on upstream Ceph.

Comment/check-run posting stays **opt-in** (`post_comment: false` by default in samples).

### Embeddings

Unchanged: local `sentence-transformers/all-MiniLM-L6-v2` on CPU, TF-IDF fallback when the model is unavailable.

### Non-regression

Ceph batch totals are compared against the regenerated baseline (`reports/all-2026-11-02.*`). Small drift is expected when GitHub moves PRs between runs; the regression script `scripts/compare_batch_totals.py` compares open/analysed counts and category tables.

### Pain points observed

1. **Large clones** : repos like `grpc/grpc` need `limits.max_prs_analyse` or shallow workflows for CI time budgets.
2. **Default branch names** : profiles must set `default_base` (`main` vs `master`).
3. **Tracker plugins** : GitHub Issues adapter needs `GITHUB_TOKEN` for rate limits; Redmine needs polite delays.
4. **Component rules** : new repos need at least coarse `path_rules` or reports bucket everything into `other`.
5. **Separate data dirs** : multi-repo runs on one machine should use distinct `paths.raw_dir` / `clone_dir` per profile (see `configs/requests.yml`).
