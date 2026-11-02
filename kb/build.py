"""Build or update a KB snapshot from cached data/ or read-only GitHub pulls."""

import json
import shutil
import tarfile
from datetime import datetime, timezone
from pathlib import Path

from triage.collect import clean_body, load_list
from triage.components import primary_component
from triage.github_api import list_open_pulls

from pr_triage.safepath import SafePath, allowed_base, resolve_under

from .indexes import build_indexes
from .schema import KB_VERSION


def _record_from_api(pr, git_info=None):
    info = git_info or {}
    rec = {
        "number": pr["number"],
        "url": pr["html_url"],
        "title": pr["title"],
        "body": clean_body(pr.get("body")),
        "author": pr["user"]["login"],
        "created_at": pr["created_at"],
        "updated_at": pr["updated_at"],
        "base": pr["base"]["ref"],
        "draft": pr.get("draft", False),
        "labels": [l["name"] for l in pr["labels"]],
        "head_sha": info.get("head_sha") or pr.get("head", {}).get("sha"),
        "git": info,
        "enriched": bool(info.get("eff_files") or info.get("files")),
    }
    from triage.tracker import tickets

    rec["tickets"] = tickets(pr["title"], pr.get("body") or "", info.get("commit_msgs", ""))
    rec["component"], rec["component_source"] = primary_component(rec)
    return rec


def merge_records(existing_by_n, fresh_records):
    for r in fresh_records:
        n = r["number"]
        old = existing_by_n.get(n)
        if old and old.get("enriched") and not r.get("enriched"):
            r = {
                **r,
                "git": old["git"],
                "enriched": True,
                "head_sha": old.get("head_sha", r.get("head_sha")),
                "staleness": old.get("staleness", r.get("staleness")),
                "precomputed_fixed": old.get("precomputed_fixed", r.get("precomputed_fixed")),
                "precomputed_backport": old.get("precomputed_backport", r.get("precomputed_backport")),
            }
        existing_by_n[n] = r
    return list(existing_by_n.values())


def _git_enriched(git_info: dict) -> bool:
    if not git_info or git_info.get("error"):
        return False
    return bool(git_info.get("eff_files") or git_info.get("files"))


def _precomputed_from_enriched(src: dict) -> dict:
    """Fields computed at nightly enrich time (merge-tree, files-gone, fixed, backport)."""
    out = {}
    for key in ("staleness", "precomputed_fixed", "precomputed_backport"):
        if src.get(key) is not None:
            out[key] = src[key]
    g = src.get("git") or {}
    if g.get("conflicts") is not None and "precomputed_merge" not in src:
        out["precomputed_merge"] = {
            "conflicts": g.get("conflicts"),
            "conflict_files": g.get("conflict_files", [])[:10],
        }
    elif src.get("precomputed_merge") is not None:
        out["precomputed_merge"] = src["precomputed_merge"]
    return out


def build_snapshot(
    out_dir: Path,
    *,
    repo="ceph/ceph",
    raw_dir=None,
    prs_cache=None,
    enriched_records=None,
    limitations=None,
    base_tips=None,
):
    """Write snapshot under out_dir. Merges API list with optional enriched git analysis."""
    root = allowed_base()
    raw_dir = resolve_under(raw_dir or "data/raw", root)
    prs_cache = SafePath(prs_cache or "data/prs.json", root)
    snap = SafePath(out_dir, root)
    snap.mkdir(parents=True, exist_ok=True)

    prs = load_list(raw_dir) if list(raw_dir.glob("pulls_open_p*.json")) else list_open_pulls(repo, raw_dir)
    enriched_by_n = {r["number"]: r for r in (enriched_records or [])}
    if prs_cache.exists() and not enriched_by_n:
        cache = json.loads(prs_cache.read_text())
        for r in cache.get("all", []):
            enriched_by_n[r["number"]] = r

    by_n = {}
    for pr in prs:
        n = pr["number"]
        git_info = enriched_by_n.get(n, {}).get("git", {})
        rec = _record_from_api(pr, git_info)
        if enriched_by_n.get(n):
            src = enriched_by_n[n]
            git_block = src.get("git") or git_info
            rec.update(
                {
                    "new_tickets": src.get("new_tickets", rec["tickets"]),
                    "primary_tickets": src.get("primary_tickets", []),
                    "commit_authors": src.get("commit_authors", []),
                    "enriched": _git_enriched(git_block),
                    "git": git_block,
                    "head_sha": src.get("head_sha") or rec.get("head_sha"),
                    **_precomputed_from_enriched(src),
                }
            )
        by_n[n] = rec

    records = sorted(by_n.values(), key=lambda r: r["number"])
    indexes = build_indexes([r for r in records if r.get("enriched")])

    manifest = {
        "kb_version": KB_VERSION,
        "repo": repo,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "n_open": len(records),
        "n_enriched": sum(1 for r in records if r.get("enriched")),
        "indexes": {k: len(v) for k, v in indexes.items()},
    }
    if base_tips:
        manifest["base_tips"] = base_tips

    (snap / "manifest.json").write_text(json.dumps(manifest, indent=2))
    with (snap / "prs.jsonl").open("w") as fh:
        for r in sorted(records, key=lambda x: x["number"]):
            fh.write(json.dumps(r, separators=(",", ":")) + "\n")
    idx_dir = snap / "indexes"
    idx_dir.mkdir(exist_ok=True)
    for name, data in indexes.items():
        (idx_dir / f"{name}.json").write_text(json.dumps(data))
    meta = snap / "meta"
    meta.mkdir(exist_ok=True)
    (meta / "limitations.json").write_text(json.dumps(limitations or [], indent=2))
    tracker_src = resolve_under("data/tracker", root)
    if tracker_src.is_dir():
        dst = snap / "tracker"
        if dst.exists():
            shutil.rmtree(dst.path)
        shutil.copytree(tracker_src, dst.path)
    return manifest


def pack_snapshot(snapshot_dir: Path, archive: Path):
    root = allowed_base()
    snapshot_dir = resolve_under(snapshot_dir, root)
    archive = resolve_under(archive, root)
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "w:gz") as tf:
        tf.add(snapshot_dir, arcname=snapshot_dir.name)
    return archive
