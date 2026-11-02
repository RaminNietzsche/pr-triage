"""Build the per-PR dataset: all open PRs (label="all") or one component such as RGW."""
import glob
import json
import re
from pathlib import Path

from .gitdata import Git, analyse_pr
from .tracker import tickets

TEMPLATE_CUT = re.compile(r"(?is)(<!--.*?-->)|(^##\s*(contribution guidelines|checklist).*)", re.M)


def clean_body(body):
    body = body or ""
    body = re.sub(r"(?s)<!--.*?-->", "", body)
    m = re.search(r"(?im)^#+\s*(contribution guidelines|checklist)", body)
    if m:
        body = body[: m.start()]
    return body.strip()


def load_list(raw_dir: Path):
    return [p for f in sorted(glob.glob(str(raw_dir / "pulls_open_p*.json"))) for p in json.loads(Path(f).read_text())]


def is_component(pr, info, label, path_prefix):
    return any(l["name"] == label for l in pr["labels"]) or any(
        f["path"].startswith(path_prefix) or f["old_path"].startswith(path_prefix) for f in info.get("files", []))


def skipped_out(out, allrec, skipped):
    out.write_text(json.dumps({"all": allrec, "skipped_missing_ref": skipped}))
    return skipped


def collect(raw_dir: Path, repo_dir: str, out: Path, label="rgw", path_prefix="src/rgw/"):
    git = Git(repo_dir)
    prs, records, skipped = load_list(raw_dir), [], []
    cache = json.loads(out.read_text()) if out.exists() else {}
    cache = {r["number"]: r for r in cache.get("all", [])} if isinstance(cache, dict) else {}
    allrec = []
    for i, pr in enumerate(prs):
        n = pr["number"]
        c = cache.get(n)
        if c and c.get("head_sha") and c.get("updated_at") == pr["updated_at"]:
            info = c["git"]
        else:
            try:
                info = analyse_pr(git, n, pr["base"]["ref"])
            except Exception as e:  # keep going; record the error
                info = {"error": str(e)[:300]}
        rec = {
            "number": n, "url": pr["html_url"], "title": pr["title"], "body": clean_body(pr["body"]),
            "author": pr["user"]["login"], "created_at": pr["created_at"], "updated_at": pr["updated_at"],
            "base": pr["base"]["ref"], "draft": pr.get("draft", False),
            "labels": [l["name"] for l in pr["labels"]], "head_sha": info.get("head_sha"), "git": info,
        }
        rec["tickets"] = tickets(pr["title"], pr["body"], info.get("commit_msgs", ""))
        allrec.append(rec)
        if info.get("error") == "missing ref":
            skipped.append(n)
        if (i + 1) % 200 == 0:
            print(f"  analysed {i + 1}/{len(prs)}")
    from .components import primary_component
    for r in allrec:
        r["component"], r["component_source"] = primary_component(r)
    if label == "all":
        return allrec, allrec, skipped_out(out, allrec, skipped)
    comp = [r for r in allrec if is_component({"labels": [{"name": x} for x in r["labels"]]}, r["git"], label, path_prefix)]
    out.write_text(json.dumps({"all": allrec, "skipped_missing_ref": skipped}))
    return comp, allrec, skipped
