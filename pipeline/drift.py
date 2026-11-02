"""Classify agreement misses as snapshot drift vs real pipeline gaps."""

from __future__ import annotations

from pathlib import Path


def _norm_sha(sha: str | None) -> str:
    if not sha:
        return ""
    return sha.strip().lower()[:12]


def load_batch_snapshot(path: Path | None = None) -> dict:
    import json

    from pr_triage.safepath import SafePath, allowed_base

    snap = SafePath(path or "reports/batch-snapshot-2026-11-02.json", allowed_base())
    return json.loads(snap.read_text())


def base_tip_drift(pr_base: str, kb_manifest: dict, batch_meta: dict) -> bool:
    kb_tips = (kb_manifest or {}).get("base_tips") or {}
    batch_tips = (batch_meta or {}).get("base_tips") or {}
    kb = _norm_sha(kb_tips.get(pr_base))
    batch = _norm_sha(batch_tips.get(pr_base))
    if not kb or not batch:
        return False
    return kb != batch


def pr_head_drift(kb_record: dict, github_pull: dict | None) -> bool:
    """True when GitHub head sha differs from KB row (PR updated since KB build)."""
    if not github_pull:
        return False
    kb_sha = _norm_sha(kb_record.get("head_sha") or (kb_record.get("git") or {}).get("head_sha"))
    live = _norm_sha(github_pull.get("head", {}).get("sha"))
    return bool(kb_sha and live and kb_sha != live)


def pr_updated_drift(kb_record: dict, github_pull: dict | None) -> bool:
    if not github_pull:
        return False
    return (kb_record.get("updated_at") or "") != (github_pull.get("updated_at") or "")


def structural_context_drift(
    pr_number: int,
    pr_base: str,
    kb_record: dict,
    *,
    kb_manifest: dict,
    batch_meta: dict,
    github_pull: dict | None = None,
) -> dict:
    """Drift signals for merge-conflict / files-gone (base-tip and PR-head sensitive)."""
    base_drift = base_tip_drift(pr_base, kb_manifest, batch_meta)
    head_drift = pr_head_drift(kb_record, github_pull)
    updated_drift = pr_updated_drift(kb_record, github_pull)
    any_drift = base_drift or head_drift or updated_drift
    return {
        "pr": pr_number,
        "base_branch": pr_base,
        "base_tip_drift": base_drift,
        "head_sha_drift": head_drift,
        "updated_at_drift": updated_drift,
        "structural_drift": any_drift,
    }


def classify_miss(miss_key: tuple, drift_info: dict, *, structural_categories: frozenset) -> str:
    cat = miss_key[0] if miss_key else ""
    if cat in structural_categories and drift_info.get("structural_drift"):
        return "drift"
    if drift_info.get("structural_drift"):
        return "drift"
    return "real_miss"
