#!/usr/bin/env bash
# Clone the configured GitHub repo and fetch open PR heads as refs/pr/<N>.
# Usage: CONFIG=configs/requests.yml ./scripts/setup_clone.sh
set -euo pipefail
cd "$(dirname "$0")/.."
CONFIG=${CONFIG:-configs/ceph.yml}
read -r REPO CLONE <<< "$(python3 - <<PY
import yaml
from pathlib import Path
d = yaml.safe_load(Path("$CONFIG").read_text())
gh = d.get("github") or {}
print(gh.get("repo","ceph/ceph"), gh.get("clone_dir","data/repo/ceph"))
PY
)"
DEFAULT_BRANCH=$(python3 - <<PY
import yaml
from pathlib import Path
d = yaml.safe_load(Path("$CONFIG").read_text())
print((d.get("github") or {}).get("default_base","main"))
PY
)
RAW=${PR_TRIAGE_RAW:-$(python3 - <<PY
import yaml
from pathlib import Path
d = yaml.safe_load(Path("$CONFIG").read_text())
print((d.get("paths") or {}).get("raw_dir", "data/raw"))
PY
)}
[ -d "$CLONE" ] || git clone --single-branch --branch "$DEFAULT_BRANCH" "https://github.com/${REPO}.git" "$CLONE"
python3 - <<PY > /tmp/pr-triage-specs
import glob, json
from pathlib import Path
raw = Path("$RAW")
prs = [p for f in sorted(glob.glob(str(raw / "pulls_open_p*.json"))) for p in json.loads(Path(f).read_text())]
print(" ".join(sorted({f"+refs/heads/{p['base']['ref']}:refs/remotes/origin/{p['base']['ref']}" for p in prs})))
for p in prs:
    print(p["number"])
PY
head -1 /tmp/pr-triage-specs | xargs -r git -C "$CLONE" fetch -q origin
git -C "$CLONE" ls-remote origin 'refs/pull/*/head' | awk '{print $2}' > /tmp/pr-triage-remote
tail -n +2 /tmp/pr-triage-specs | while read -r n; do
  grep -qx "refs/pull/$n/head" /tmp/pr-triage-remote && echo "+refs/pull/$n/head:refs/pr/$n"
done | xargs -n 300 -r git -C "$CLONE" fetch -q origin
echo "done: $(git -C "$CLONE" for-each-ref refs/pr 2>/dev/null | wc -l) PR refs for ${REPO}"
