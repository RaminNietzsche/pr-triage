#!/usr/bin/env bash
# One-command, from-scratch run of ceph-pr-triage (read-only on GitHub and tracker.ceph.com).
#   ./triage.sh [run.py options...]      e.g. ./triage.sh --component rgw --path-prefix src/rgw/
# Steps: create .venv + install deps, cache the open-PR list, clone ceph/ceph and fetch
# open PR heads, then analyse and write reports/. Re-running is incremental.
set -euo pipefail
export PYTHONUNBUFFERED=1
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
if [[ ! -x .venv/bin/python ]]; then
  "$PY" -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q --index-url https://download.pytorch.org/whl/cpu torch
  .venv/bin/pip install -q -r requirements.txt
fi
.venv/bin/python run.py --list-only "$@"
scripts/setup_clone.sh
.venv/bin/python run.py "$@"
