"""Default high-precision finding filter for maintainer-facing output."""

from kb.schema import HIGH_PRECISION_CATEGORIES


def is_high_precision(finding: dict) -> bool:
    cat = finding["category"]
    conf = finding["confidence"]
    base_cat = cat.split(" (")[0] if cat.startswith("already-in-base") else cat
    if base_cat not in HIGH_PRECISION_CATEGORIES and not cat.startswith("already-in-base"):
        return False
    if cat == "merge-conflict":
        return conf == "high"
    if cat == "files-gone":
        return conf == "high"
    if cat.startswith("already-in-base"):
        return conf == "high"
    if cat in ("duplicate", "duplicate-backport"):
        return conf == "high" or (
            conf == "medium" and "identical" in finding.get("reason", "").lower()
        )
    if cat == "stated-supersede":
        return conf in ("high", "medium")
    if cat == "ticket-closed":
        return conf == "medium" and "fix reported landed" in finding.get("reason", "")
    return conf == "high"


def filter_findings(findings, *, all_findings=False):
    if all_findings:
        return findings
    return [f for f in findings if is_high_precision(f)]
