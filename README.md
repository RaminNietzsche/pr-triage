# pr-triage

https://github.com/RaminNietzsche/pr-triage

A **read-only**, **config-driven** triage assistant for open pull request backlogs.
The reference profile targets [ceph/ceph](https://github.com/ceph/ceph); other
repositories use YAML profiles under `configs/`. It finds open PRs that are probably
duplicates, superseded, already merged in another form, blocked by conflicts,
or linked to tracker tickets that are already closed, and writes a report with
the evidence for each finding so that a human can decide what to do.

It never comments, labels, closes, reviews or messages anyone. The only network
operations are HTTP `GET`s to the GitHub REST API (the open-PR list),
`git clone`/`git fetch` of the public repository, and `GET`s to the public
tracker.ceph.com Redmine API. Every finding is a *candidate for human review*,
not a verdict.

Status: prototype, personal project by Ramin Najarbashi. Not affiliated with or
endorsed by the Ceph project.

## Quick start (new repository)

Requirements: Linux or macOS, `python3` (3.10+), `git` 2.38+ (for `git merge-tree`),
network access to github.com, and optional local embeddings (PyTorch + sentence-transformers).

1. Copy or author `configs/myrepo.yml` (see `configs/requests.yml` for a minimal example).
2. Optionally add `.pr-triage.yml` with `config: configs/myrepo.yml`.
3. Run:

```bash
pip install -r requirements.txt
python -m pr_triage batch --config configs/myrepo.yml --list-only --refresh
CONFIG=configs/myrepo.yml ./scripts/setup_clone.sh
python -m pr_triage batch --config configs/myrepo.yml
```

Subcommands: `batch`, `build-kb`, `per-pr` (all accept `--config`). Design notes:
`docs/generic-pipeline-design.md`.

## Quick start (Ceph reference profile)

Requirements include tracker.ceph.com for ticket status unless you pass `--no-tracker`.

```bash
./triage.sh                         # all open PRs (default → configs/ceph.yml)
./triage.sh --component rgw         # one component: label `rgw` or files under src/rgw/
./triage.sh --component cephfs --path-prefix src/mds/
# equivalent:
python -m pr_triage batch --config configs/ceph.yml --component all
```

`triage.sh` does everything from an empty checkout:

1. creates `.venv` and installs `requirements.txt` (CPU-only PyTorch);
2. downloads and caches the open-PR list (`run.py --list-only`);
3. clones ceph/ceph and fetches every open PR head as `refs/pr/<N>`
   (`scripts/setup_clone.sh`; refs that disappeared are skipped);
4. analyses the PRs and writes `reports/<scope>-<date>.md` and `.csv`, plus
   `data/analysis-<scope>-<date>.json`.

### Per-PR pipeline (prototype)

For maintainer-facing workflows, build a KB snapshot and query one PR without a
full batch re-scan:

```bash
python run.py --list-only
scripts/fetch_pr_subset.sh 71234    # or scripts/setup_clone.sh for full index
python -c "from pathlib import Path; from kb.build import build_snapshot; from kb.enrich import enrich_prs; \
  build_snapshot(Path('data/kb-snapshot'), enriched_records=enrich_prs(Path('data/raw'), 'data/repo/ceph'))"
python per_pr.py --pr 71234 --kb data/kb-snapshot --render
```

Architecture and hosting options: see the project doc
`docs/per-pr-pipeline-architecture.md` in Context. Sample workflow:
`docs/examples/per-pr-triage.workflow.yml.sample`.

Re-runs are incremental: the clone is fetched rather than re-cloned, per-PR git
analysis is reused while a PR's `updated_at` is unchanged, and tracker lookups are
cached for 24 hours. A first run takes about 27 minutes for the RGW scope and roughly
an hour for all open PRs (mostly cloning, per-PR git analysis and the
rate-limited tracker lookups).

Options (`run.py`, also accepted by `triage.sh`):

| flag | meaning |
|---|---|
| `--component all\|<label>` | scope; `all` (default) or one component label |
| `--path-prefix PATH` | with a component, also select PRs touching PATH (default `src/<label>/`) |
| `--refresh` | re-download the open-PR list instead of using the cache |
| `--no-tracker` | skip tracker.ceph.com lookups |
| `--clone DIR` | location of the local clone (default `data/repo/ceph`) |

Environment: `GITHUB_TOKEN` is optional and only raises the GitHub rate limit
(anonymous: 60 requests per hour; a run needs about 20).

## What it reports

| category | signal |
|---|---|
| `merge-conflict` | `git merge-tree --write-tree` of the PR head into the current base tip conflicts |
| `files-gone` | the PR's own unmerged commits modify files that no longer exist on the base tip (with the commit that removed or renamed them) |
| `inactive>1y` | no update for 365 days (the `pinned` label is shown) |
| `duplicate` | identical effective patch or identical commit set (high); same title, or near-identical text from different authors, with overlapping files (medium) |
| `stated-supersede` | the PR description says it continues, supersedes or consolidates another open PR |
| `competing-fix` | different authors (PR and commit authors), same tracker ticket, overlapping hunks |
| `overlapping-backports`, `duplicate-backport` | release-branch PRs that cherry-pick the same main commits |
| `already-in-base` | `git cherry` finds the PR's commits already on the base, or another author's base commit for the same ticket touches the same files |
| `ticket-closed`, `ticket-partly-closed` | all or some of the PR's primary tracker tickets are closed (status and date recorded) |
| `backport-source-not-on-main` | a backport's `cherry picked from` commit is not on main (following trailers recursively) and main has no same-subject commit |
| `backport-trailer-sha-mismatch` | the trailer SHA is not on main but a same-subject commit is (usually a typo or a re-cut commit) |
| `stacked`, `shares-commits`, `related-series`, `possible-overlap` | informational relations between branches |
| `needs-rebase-label-but-clean` | informational only: local merge is clean but GitHub often still reports a conflict (see precision) |

All PR-to-PR signals are computed on each PR's **effective change**: what merging
it into today's base tip would change. Stale branches that still carry merged
commits therefore do not produce false overlap. Text similarity uses the local
`sentence-transformers/all-MiniLM-L6-v2` model on CPU (title, cleaned description,
commit subjects, file list and added lines), with a TF-IDF fallback. No hosted AI
API is used and no PR content leaves the machine.

Each PR gets one primary **component** for the per-component breakdown: the
component label that most of its files belong to (labels are often applied
automatically from paths), or, for PRs without a component label, a path-based
guess (`triage/components.py`).

### Tracker tickets

Tickets are read with `GET https://tracker.ceph.com/issues/<id>.json`, one request
per second, cached under `data/tracker/`. Only *primary* tickets count: ones the PR
says it fixes or tracks (`Fixes:`, `Resolves:`, `Closes:`, backport `tracker:` lines,
or a tracker URL alone on a line), not tickets cited as context. For release-branch
backports only `Backport` tickets count. QA-run tickets are ignored.

## Precision

Findings were checked by hand against the underlying evidence (diffs and commits,
`git log` on the base, tracker JSON, and GitHub's `mergeable` flag for a few PRs).

* RGW (406 PRs): up to 30 findings per category, 169 findings in total. The
  detectors were then fixed and re-checked. Details:
  `reports/precision-review-2026-11-02.csv` and the "Precision review" section of
  the report.
* Other components: a stratified spot-check of 20 findings, of which 14 were correct.
  Four of the six false positives led to detector fixes; the other two were the
  known GitHub disagreement case. Details: `reports/precision-spotcheck-nonrgw-2026-11-02.csv`.

Reproduce the evidence dumps with `review/evidence.py`; the verdicts are recorded
in `review/verdicts_2026-11-02.py` and `review/spotcheck_nonrgw_2026-11-02.py`.

## Config reference

| Key | Purpose |
|-----|---------|
| `github.repo` | `owner/name` on GitHub |
| `github.default_base` | Primary integration branch (`main`, `master`, …) |
| `github.release_branches` | Backport bases for ticket/backport logic |
| `components.label_priority` / `path_rules` | Map labels and paths → component |
| `tracker.plugin` | `redmine`, `github_issues`, `jira`, or `none` |
| `tracker.issue_id_regex` | Regex with one capture group for ticket id |
| `thresholds.inactive_days` | Inactivity finding threshold |
| `limits.max_prs_analyse` | Optional cap for smoke runs on huge backlogs |
| `paths.raw_dir`, `github.clone_dir` | Isolated caches per profile |

Full Ceph rules: `configs/ceph.yml`.

## Layout

```
pr_triage/                 config loader, CLI, tracker adapters, batch runner
configs/                   repo profiles (ceph, requests, grpc, …)
.pr-triage.yml             default profile pointer
triage.sh                  one-command setup and run (Ceph)
run.py                     legacy entry point → pr_triage.batch
scripts/setup_clone.sh     clone + fetch of open PR heads (CONFIG=…)
triage/github_api.py       read-only GitHub REST client with on-disk cache and retries
triage/gitdata.py          per-PR git analysis (files, hunks, patch-ids, merge-tree, git cherry)
triage/collect.py          dataset and scope selection
triage/components.py       primary component per PR
triage/tracker.py          tracker ticket parsing (all and primary references)
triage/tracker_api.py      read-only tracker.ceph.com client, ticket findings
triage/dupes.py            embeddings + structural pair classification
triage/xref.py             author-stated cross references between PRs
triage/staleness.py        conflicts, removed files, inactivity
triage/fixed.py            already-in-base and backport source checks
triage/report.py           markdown + CSV, per-component table
review/                    precision review scripts and recorded verdicts
reports/                   generated reports (dated)
docs/proposal.md           proposal for the Ceph community
.github/workflows/weekly-triage.yml.sample   sample report-only CI job (not enabled)
data/                      caches (gitignored)
```

## Limitations

* Mergeability is simulated locally with `git merge-tree`. GitHub's own flag can
  be stale in both directions, so conflicts are reported against the base tip at
  snapshot time.
* Similarity is heuristic; low-confidence pairs are usually related work.
* A closed or shared tracker ticket does not prove a PR is obsolete: tickets often
  get several partial fixes, follow-ups and backports.
* `git cherry` only catches textually equivalent patches.
* `updated_at` also moves on bot and label activity, so inactivity is under-counted.
* The PR list, the clone and the tracker are read minutes apart; PRs merged in
  between can show up as findings.

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE). Copyright Ramin Najjarbashi.
