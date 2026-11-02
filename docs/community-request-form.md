# Ceph Foundation Community Request (draft)

**Project name:** pr-triage (read-only open-PR triage assistant)

**License:** Apache-2.0

**Public repository:** https://github.com/RaminNietzsche/pr-triage

**Contact:** ramin.najarbashi@gmail.com (Ramin Najjarbashi, personal project)

## Summary

pr-triage is a local, read-only tool that scans a GitHub repository's open pull
requests and produces a Markdown/CSV report of *candidates* for human review:
merge conflicts with the current base, files removed on the base, commits already
landed, duplicate or competing PRs, closed tracker tickets, and related signals.
It never comments, labels, closes, or reviews anything on GitHub or on external
trackers.

## Problem

Large projects such as ceph/ceph carry thousands of open PRs. Reviewers spend
time finding PRs that cannot merge as-is, are superseded, or point at closed
tracker work. Manual comparison of branches and tracker history does not scale.

## Proposed pilot

- **Component:** RGW (reference config `configs/ceph.yml`, path prefix `src/rgw/`)
- **Mode:** report-only; artifacts published weekly (GitHub Actions artifact or
  digest), no automated changes to PRs or tickets
- **Measured precision:** stratified samples on the Ceph backlog show low false-
  positive rates on high-confidence categories after recent detector work (see
  `docs/proposal.md`)

## What we ask from the Foundation / community

1. Feedback from maintainers on which report categories are useful vs noise
2. A maintainer or component lead willing to skim occasional reports and say
   whether they save review time
3. No requirement to run hosted infrastructure: the tool runs on GitHub Actions
   with read-only permissions or on a volunteer machine

## Outreach order

1. **First:** post a short announcement and ask for feedback on **ceph-devel@ceph.io**
   (see `docs/ceph-devel-email.md`)
2. **Then:** submit this Community Request form once there is maintainer feedback

## Safety

- HTTP GET only toward GitHub and configured trackers (Redmine for Ceph)
- No write access to ceph/ceph or tracker.ceph.com
- Findings are suggestions; humans decide all actions
