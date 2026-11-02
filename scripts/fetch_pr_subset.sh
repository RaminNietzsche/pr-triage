#!/usr/bin/env bash
# Fetch only listed PR heads (+ their base branches) into data/repo/ceph. Read-only.
set -euo pipefail
cd "$(dirname "$0")/.."
CLONE=data/repo/ceph
NUMBERS=("$@")
[ ${#NUMBERS[@]} -gt 0 ] || { echo "usage: fetch_pr_subset.sh PR [PR...]" >&2; exit 1; }
[ -d "$CLONE" ] || git clone --single-branch --branch main https://github.com/ceph/ceph.git "$CLONE"
BASES=$(python3 - "$@" <<'PY'
import glob, json, sys
nums = {int(x) for x in sys.argv[1:]}
prs = [p for f in sorted(glob.glob("data/raw/pulls_open_p*.json")) for p in json.load(open(f))]
bases = sorted({p["base"]["ref"] for p in prs if p["number"] in nums})
print(" ".join(f"+refs/heads/{b}:refs/remotes/origin/{b}" for b in bases))
PY
)
# shellcheck disable=SC2086
[ -n "$BASES" ] && git -C "$CLONE" fetch -q origin $BASES
git -C "$CLONE" ls-remote origin 'refs/pull/*/head' | awk '{print $2}' > /tmp/ceph-triage-remote
SPECS=""
for n in "${NUMBERS[@]}"; do
  grep -qx "refs/pull/$n/head" /tmp/ceph-triage-remote && SPECS="$SPECS +refs/pull/$n/head:refs/pr/$n"
done
# shellcheck disable=SC2086
[ -n "$SPECS" ] && git -C "$CLONE" fetch -q origin $SPECS
echo "fetched ${#NUMBERS[@]} PR refs"
