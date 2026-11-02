# Proposal: a read-only, report-only triage aid for the ceph/ceph PR backlog

*By Ramin Najjarbashi. Personal project; not affiliated with any company.*
*License: Apache-2.0. Code: https://github.com/RaminNietzsche/pr-triage*
*Contact: ramin.najarbashi@gmail.com*
*Outreach plan: ceph-devel@ceph.io first, then Ceph Foundation Community Request.*
*Pilot component: RGW.*

## Problem

ceph/ceph has about 1,850 open pull requests. Many of them can no longer be merged
as they are, have been overtaken by other work, or still point at tracker tickets
that were closed long ago. Finding them takes reviewer time: you have to compare
branches, read tracker history and check what already landed on main or on a
release branch. Backports raise the cost further, because the same change exists
once per branch.

## What the tool does

`ceph-pr-triage` is a small, local, **read-only** analysis tool. It never
comments, labels, closes or reviews anything. It reads the public open-PR list, a
local clone with every PR head (`refs/pull/N/head`), and the public tracker.ceph.com
API. It then writes a Markdown/CSV report in which each finding has its evidence
and a confidence level:

- **Mergeability:** `git merge-tree` of each PR into today's base tip (conflicts),
  plus files the PR modifies that were removed or renamed on the base, with the
  commit that removed them.
- **Already landed:** `git cherry` and patch-ids find PR commits already on the
  base. Another author's base commit for the same tracker ticket, touching the
  same files, is also reported.
- **Overlap between PRs:** identical effective patches, stacked branches, shared
  commits, competing fixes for one ticket from different authors, backports
  cherry-picking the same commits, and PR descriptions that say they supersede
  another PR. Text similarity uses a small local embedding model (CPU only). No
  hosted AI service is used, and no data leaves the machine.
- **Tracker status:** a PR's primary tickets (the ones it says it fixes) that are
  Resolved, Rejected, Duplicate, Won't Fix and so on.
- **Backport hygiene:** `cherry picked from` sources that are not on main, or
  trailer SHAs that do not exist.

All PR-to-PR signals use each PR's *effective change* (what merging it today would
change), so old branches that still carry merged commits do not create false matches.

## Sample run (2 November 2026, all open PRs)

Fresh from-scratch verify on 2 November 2026 (`./triage.sh --component all`, tracker
lookups enabled):

| | |
|---|---|
| open PRs analysed | 1,850 of 1,851 (one head ref could not be fetched) |
| findings total | 707 |
| PRs with at least one actionable finding | 370 |
| conflict with the current base tip | 308 |
| files removed from the base | 22 PRs |
| commits already on the base | 43 PRs |
| all primary tickets closed / some closed | 18 / 18 PRs |
| duplicates (identical patch or same title) | 8 pairs |
| backports whose source is not on main | 7 |
| informational relations (stacked, shared commits, series) | 251 |

Per component (primary component, flagged / PRs): rgw 90/381, dashboard 63/133,
cephadm 41/190, core 41/254, cephfs 34/298, crimson 20/53, mon 16/70, rbd 15/59.

## Measured precision

Two stratified re-samples (up to 30 findings per category) on the 2 November 2026
all-PR run, using automated git/tracker rules plus conservative defaults (uncertain
→ TP). Details: `docs/detector-tightening-2026-11-02.md` in the project store.

| | Seed 17 (pre-tightening snapshot) | Seed 42 (after detector tightening) |
|---|---|---|
| Sampled findings | 286 | 280 |
| Overall FP rate | 8% (23/286) | 4% (11/280) |
| Actionable FP rate | 7% (12/178) | **0%** (0/173) |
| ticket-closed FP | 28% (5/18) | **0%** (0/23) |
| already-in-base FP (all variants, seed-17 CSV) | **14%** (6/43) | **0%** (0/27) |

Actionable categories exclude stacked/shared-commit/series overlap and
**needs-rebase-label-but-clean** (100% FP vs local `git merge-tree`; GitHub's
mergeable flag often disagrees; informational only).

After tightening, the full run dropped **43 → 27** already-in-base findings (fewer
partial-cherry and same-author follow-up rows). Merge-conflict, files-gone,
duplicate, backport-*, competing-fix, and overlapping-backports remained **0%** FP
in both samples.

Earlier manual reviews (seeds 0/1, RGW-focused and a 20-finding non-RGW spot-check)
motivated earlier fixes; seeds 17 and 42 bracket the latest detector pass on the
full backlog.

## What I am asking for

1. **Feedback** from maintainers and component leads:
   - Which categories are useful?
   - Which are noise?
   - Which signals are missing (for example Teuthology results or reviewer state)?
2. **A sponsor or maintainer champion** who would look at a report now and then
   and tell me whether it saves time. Component leads for RGW, CephFS or the
   dashboard would be ideal, since those components have the most flagged PRs.
3. **Agreement to a weekly, report-only run.**
   - It would run as a scheduled job (a sample GitHub Actions workflow with
     `permissions: contents: read` is included) or on my own machine.
   - The report would be published as an artifact or a mailing-list digest.
   - It would **never** auto-close, label, comment on or otherwise change any PR
     or ticket. Every action stays with humans.

I'm happy to change the scope, output format or schedule to suit the project's
workflow, and I'd drop any category the maintainers find unhelpful.

Contact: ramin.najarbashi@gmail.com (list: ceph-devel@ceph.io).
