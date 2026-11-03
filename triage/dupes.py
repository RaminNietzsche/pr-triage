"""Duplicate / near-duplicate detection.

Text similarity (local sentence-transformers model, TF-IDF fallback) combined
with structural signals computed on each PR's *effective* change (commits not
yet in base): identical patch-ids, commit-set containment (stacked PRs),
shared cherry-pick sources (backports), shared tracker tickets, overlapping
files and overlapping pre-image hunks."""
import itertools
import re

import numpy as np

MODEL = "sentence-transformers/all-MiniLM-L6-v2"
_MODEL = None


def pr_text(r, max_diff_chars=3000):
    g = r["git"]
    subjects = [m.split("\n", 1)[0] for m in g.get("new_commit_msgs", "").split("\n\n") if m][:20]
    added = "\n".join(l[1:] for l in g.get("diff", "").splitlines() if l.startswith("+") and not l.startswith("+++"))
    files = " ".join(g.get("eff_files", [])[:40])
    return f"{r['title']}\n{r['body'][:1500]}\n{' | '.join(subjects)}\nFILES: {files}\n{added[:max_diff_chars]}"


def embed(texts):
    global _MODEL
    try:
        from sentence_transformers import SentenceTransformer
        if _MODEL is None:
            _MODEL = SentenceTransformer(MODEL, device="cpu")
        v = _MODEL.encode(texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(v), "sentence-transformers all-MiniLM-L6-v2 (local, CPU)"
    except Exception as e:  # offline / install failure
        import warnings

        warnings.warn(
            f"sentence-transformers unavailable ({e}); using TF-IDF for duplicate similarity",
            stacklevel=2,
        )
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.preprocessing import normalize
        v = TfidfVectorizer(max_features=50000, sublinear_tf=True, stop_words="english").fit_transform(texts)
        return normalize(v).toarray(), "TF-IDF (fallback)"


def hunk_overlap(a, b):
    n = 0
    for f in set(a) & set(b):
        for s1, e1 in a[f]:
            for s2, e2 in b[f]:
                if s1 < e2 and s2 < e1:
                    n += 1
    return n


def norm_title(t):
    from pr_triage.context import get_config

    prefixes = tuple(p.lower() for p in get_config().tracker.branch_title_prefixes)
    tl = t.lower()
    if prefixes and tl.startswith(prefixes):
        t = re.sub(r"^(\w[\w-]*:\s*)?", "", tl)
    else:
        t = tl
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def classify(a, b, s):
    """Return (kind, confidence, evidence dict) or None for a same-base pair."""
    ga, gb = a["git"], b["git"]
    fa, fb = set(ga.get("eff_files", [])), set(gb.get("eff_files", []))
    if not fa or not fb:
        return None
    jac = len(fa & fb) / len(fa | fb)
    pa, pb = set(ga.get("new_commit_patch_ids", [])), set(gb.get("new_commit_patch_ids", []))
    ca, cb = set(ga.get("new_cherry_picked_from", [])), set(gb.get("new_cherry_picked_from", []))
    tick = sorted(set(a["new_tickets"]) & set(b["new_tickets"]), key=int)
    hunks = hunk_overlap(ga.get("eff_hunks", {}), gb.get("eff_hunks", {}))
    # same author = same PR opener, or the commits share an author (a backport opened by someone else)
    same_author = a["author"] == b["author"] or bool(set(a.get("commit_authors", ())) & set(b.get("commit_authors", ())))
    ev = {"similarity": round(s, 3), "file_jaccard": round(jac, 2), "hunk_overlaps": hunks, "shared_tickets": tick,
          "same_author": same_author, "shared_commits": len(pa & pb), "shared_cherry_picks": len(ca & cb)}
    same_eff = ga.get("eff_patch_id") and ga.get("eff_patch_id") == gb.get("eff_patch_id")
    if same_eff or (pa and pa == pb):
        return "duplicate", "high", {**ev, "why": "identical effective patch" if same_eff else "identical commit set"}
    if a["base"] != "main" and ca and cb and ca == cb:
        return "duplicate-backport", "high", {**ev, "why": "both cherry-pick exactly the same main commits"}
    if pa and pb and (pa < pb or pb < pa):
        return "stacked", "low", {**ev, "why": "one PR's new commits are a strict subset of the other's (stacked/superseding branch)"}
    if a["base"] != "main" and len(ca & cb) and len(ca & cb) >= 0.5 * min(len(ca), len(cb)):
        return "overlapping-backports", "medium", {**ev, "why": f"{len(ca & cb)} cherry-pick sources in common"}
    same_title = norm_title(a["title"]) == norm_title(b["title"])
    # spot-check: sibling PRs by one author (same infra commit, different test each) read as near-identical text
    if (same_title or (s >= 0.95 and not same_author)) and jac >= 0.3:
        return "duplicate", "medium", {**ev, "why": "same/near-identical title and description, overlapping files"}
    if len(pa & pb):
        return "shares-commits", "low", {**ev, "why": f"{len(pa & pb)} identical commits in both (shared base work or cherry-picks)"}
    # precision review: a shared ticket + shared files without overlapping hunks was a false positive
    if tick and not same_author and hunks and (jac >= 0.2 or hunks >= 3):
        return "competing-fix", "medium", {**ev, "why": "different authors, same tracker ticket, overlapping code"}
    if tick and same_author and (hunks or jac >= 0.5):
        return "related-series", "low", {**ev, "why": "same author and ticket, overlapping code (likely a split series)"}
    if s >= 0.88 and hunks:
        return "possible-overlap", "low", {**ev, "why": "high text similarity and overlapping hunks"}
    return None


def find_pairs(recs, sim_threshold=0.80):  # noqa: ARG001
    recs = [r for r in recs if r["git"].get("eff_files")]
    vecs, method = embed([pr_text(r) for r in recs])
    sims = vecs @ vecs.T
    # candidate pairs: classify() can only fire when the two PRs share an effective file,
    # a commit patch-id or a cherry-pick source, so index on those instead of all n^2 pairs
    index = {}
    for i, r in enumerate(recs):
        g = r["git"]
        keys = [("f", f) for f in g.get("eff_files", [])] + [("p", p) for p in g.get("new_commit_patch_ids", [])] \
            + [("c", c) for c in g.get("new_cherry_picked_from", [])]
        for k in set(keys):
            index.setdefault((r["base"], k), []).append(i)
    cand = set()
    for (_, k), idx in index.items():
        if k[0] == "f" and len(idx) > 300:
            continue  # files touched by hundreds of PRs (e.g. CMakeLists.txt) alone are not a useful signal
        cand.update(itertools.combinations(idx, 2))
    pairs = []
    for i, j in sorted(cand):
        a, b = recs[i], recs[j]
        if a["base"] != b["base"]:
            continue  # same change on different branches = backport family, expected
        c = classify(a, b, float(sims[i, j]))
        if c:
            pairs.append({"a": a["number"], "b": b["number"], "base": a["base"], "kind": c[0], "confidence": c[1], **c[2]})
    return pairs, method


def clusters(pairs, kinds=("duplicate", "duplicate-backport", "competing-fix")):
    parent = {}

    def f(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for p in pairs:
        if p["kind"] in kinds:
            parent[f(p["a"])] = f(p["b"])
    groups = {}
    for x in parent:
        groups.setdefault(f(x), set()).add(x)
    return [sorted(g) for g in groups.values() if len(g) > 1]
