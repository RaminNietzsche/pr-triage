"""Assign each PR one primary component, for per-component breakdowns.

Rules come from the active triage config (`components.label_priority` and `path_rules`)."""
from collections import Counter

from pr_triage.context import get_config


def _rules():
    cfg = get_config().components
    return cfg.label_priority, cfg.path_rules, cfg.generic_labels


def by_path(paths):
    _, path_rules, _ = _rules()
    c = Counter()
    for p in paths:
        for rule in path_rules:
            pre, comp = rule.prefix, rule.component
            if p.startswith(pre) or (pre.endswith(".txt") and p.endswith(pre)):
                c[comp] += 1
                break
    if not c:
        return None
    _, _, generic = _rules()
    spec = [(n, k) for k, n in c.items() if k not in generic]
    return max(spec)[1] if spec else c.most_common(1)[0][0]


def path_counts(paths):
    _, path_rules, _ = _rules()
    c = Counter()
    for p in paths:
        for rule in path_rules:
            pre, comp = rule.prefix, rule.component
            if p.startswith(pre) or (pre.endswith(".txt") and p.endswith(pre)):
                c[comp] += 1
                break
    return c


def primary_component(rec):
    label_priority, _, generic = _rules()
    labels = set(rec.get("labels", []))
    files = [f["path"] for f in rec.get("git", {}).get("files", [])]
    cands = [l for l in label_priority if l in labels]
    if len(cands) > 1:
        pc = path_counts(files)
        spec = [l for l in cands if l not in generic and pc.get(l, 0)]
        pool = spec or [l for l in cands if l not in generic] or cands
        best = max(pool, key=lambda l: (pc.get(l, 0), -label_priority.index(l)))
        return best, "label"
    if cands:
        return cands[0], "label"
    comp = by_path(files)
    return (comp, "path") if comp else ("other", "none")
