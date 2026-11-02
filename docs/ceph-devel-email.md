# Draft email for ceph-devel@ceph.io

**To:** ceph-devel@ceph.io

**Subject:** [RFC] read-only PR triage report for ceph/ceph (pilot: RGW)

Hello,

I'm Ramin Najjarbashi. I've been working on a personal, read-only tool called
**pr-triage** to help triage ceph/ceph's large open-PR backlog. It does not
comment, label, or close anything. It only reads public GitHub data, a local
git clone with PR heads, and the public tracker.ceph.com API, then writes a
report with evidence and confidence levels.

Repository (Apache-2.0): https://github.com/RaminNietzsche/pr-triage

On a recent full run (~1,850 open PRs), the tool flagged on the order of
hundreds of PRs with at least one actionable signal (merge conflicts, files
removed on the base, likely duplicates, closed primary tickets, and similar).
I've hand-reviewed samples and tightened detectors where precision was weak.

**Pilot proposal:** I'd like feedback from RGW maintainers first (`--component
rgw` / `src/rgw/`). If useful, a weekly report-only job could publish artifacts
(GitHub Actions with `contents: read` only, or a local cron). No bot would post
to GitHub unless the project explicitly opts in later.

Questions for the list:

1. Which categories in `docs/proposal.md` would be worth your time vs noise?
2. Would a weekly CSV/Markdown digest help, and where should it live?
3. Is anyone willing to be a point of contact for a short pilot?

I'm not affiliated with any vendor. Contact: ramin.najarbashi@gmail.com

Thank you,
Ramin Najjarbashi
