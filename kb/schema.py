"""KB snapshot layout and version."""

KB_VERSION = 1

# Snapshot directory layout (also packed as kb-snapshot.tar.gz):
#   manifest.json     - version, repo, built_at, stats, base_tips
#   prs.jsonl         - one JSON object per line (open PR records)
#   indexes/
#     patch_id.json   - patch-id -> [pr numbers]
#     eff_patch.json  - effective patch-id -> [pr numbers]
#     file.json       - path -> [pr numbers] (cap list length in manifest)
#     ticket.json     - tracker id -> [pr numbers]
#   tracker/          - optional copy of data/tracker cache
#   meta/
#     limitations.json

HIGH_PRECISION_CATEGORIES = frozenset({
    "merge-conflict",
    "files-gone",
    "duplicate",
    "duplicate-backport",
    "stated-supersede",
    "already-in-base",
    "ticket-closed",
})
