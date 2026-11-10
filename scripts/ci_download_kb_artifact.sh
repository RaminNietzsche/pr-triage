#!/usr/bin/env bash
# Download the latest successful workflow run artifact (KB snapshot).
# Usage: ci_download_kb_artifact.sh [workflow_file] [artifact_name] [out_dir]
# Requires: gh CLI, GITHUB_TOKEN with actions:read in the current repository.
set -euo pipefail

WORKFLOW_FILE="${1:-pr-triage-kb.yml}"
ARTIFACT_NAME="${2:-pr-triage-kb-snapshot}"
OUT_DIR="${3:-kb-artifact}"

if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI is required" >&2
  exit 1
fi

RUN_ID="$(gh run list --workflow="$WORKFLOW_FILE" --status success --limit 1 --json databaseId \
  -q '.[0].databaseId' 2>/dev/null || true)"

if [ -z "$RUN_ID" ] || [ "$RUN_ID" = "null" ]; then
  echo "No successful run found for workflow $WORKFLOW_FILE" >&2
  exit 2
fi

mkdir -p "$OUT_DIR"
rm -rf "${OUT_DIR:?}"/*
gh run download "$RUN_ID" -n "$ARTIFACT_NAME" -D "$OUT_DIR"
echo "Downloaded $ARTIFACT_NAME from run $RUN_ID -> $OUT_DIR"
