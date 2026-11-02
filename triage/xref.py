"""Explicit cross-references between open PRs stated by authors in PR descriptions.

E.g. "Continuation to PR #72100", "supersedes #NNN", "consolidates ... discussed in #NNN".
A human-written statement is the strongest duplicate/supersede evidence, but
keyword matching is crude, so only the text of the same sentence *before* the
reference is inspected and negations ("not a replacement") are dropped."""
import re


def _ref_re():
    from pr_triage.context import get_config

    repo = re.escape(get_config().github.repo)
    return re.compile(rf"(?:https?://github\.com/{repo}/pull/|(?<![\w/])#)(\d{{4,6}})\b")


STRONG = re.compile(r"continuation (?:to|of)|supersed(?:e|es|ing)|duplicate of|tak(?:es|ing) over|rebased version of|reopen(?:ed|ing)? (?:of)?", re.I)
WEAK = re.compile(r"consolidat\w*|\breplaces?\b|alternative to|instead of", re.I)
TENTATIVE = re.compile(r"\b(needed|plan|will|would|could|might|eventually|future)\b", re.I)
NEG = re.compile(r"\bnot\b|n't\b", re.I)


def _sentence_before(text, pos, maxlen=160):
    pre = text[max(0, pos - maxlen):pos]
    cut = max(pre.rfind(". "), pre.rfind("\n"), pre.rfind("; "))
    return pre[cut + 1:] if cut >= 0 else pre


def cross_refs(recs, open_numbers):
    seen, out = set(), []
    for r in recs:
        for m in _ref_re().finditer(r["body"]):
            n = int(m.group(1))
            if n == r["number"] or n not in open_numbers or (r["number"], n) in seen:
                continue
            pre = _sentence_before(r["body"], m.start())
            if NEG.search(pre):
                continue
            if STRONG.search(pre):
                conf = "high"
            elif WEAK.search(pre):
                conf = "medium"
            else:
                conf = None
            if conf and TENTATIVE.search(pre):
                conf = "low"  # stated intent, not a fact
            if conf:
                seen.add((r["number"], n))
                out.append({"from": r["number"], "to": n, "confidence": conf,
                            "quote": re.sub(r"\s+", " ", pre + m.group(0)).strip()[-200:]})
    return out
