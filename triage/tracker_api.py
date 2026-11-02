"""Ticket status lookups via configurable tracker plugins."""

from pathlib import Path

from pr_triage.context import get_config
from pr_triage.trackers import get_tracker_adapter


def _obsolete_status(cfg):
    return cfg.fix_landed_statuses | cfg.not_fixed_statuses


class Tracker:
    """Backward-compatible wrapper around a tracker adapter."""

    def __init__(self, cache_dir: Path, delay=1.0, max_age_s=24 * 3600):
        cfg = get_config().tracker
        self.dir = cache_dir
        self.delay = delay
        self.max_age = max_age_s
        self._adapter = get_tracker_adapter(cfg, cache_dir)

    def issue(self, tid):
        return self._adapter.issue(str(tid))

    def duplicate_of(self, tid):
        return self._adapter.duplicate_of(str(tid))


def duplicate_of(tracker: Tracker, tid):
    return tracker.duplicate_of(tid)


def ticket_findings(tracker: Tracker, recs):
    """PRs whose relevant linked tickets are all closed on the tracker."""
    from .tracker import primary_ticket_texts, primary_tickets

    tcfg = get_config().tracker
    obsolete_status = _obsolete_status(tcfg)
    out = []
    for r in recs:
        tids = primary_tickets(*primary_ticket_texts(r))
        if not tids:
            continue
        info = [tracker.issue(t) for t in tids]
        backport = r["base"] in tcfg.release_branches
        rel = [
            i
            for i in info
            if (i.get("tracker") == tcfg.backport_tracker_name) == backport
            and i.get("is_closed") is not None
            and not i.get("status", "").startswith("QA")
        ]
        if not rel:
            continue
        closed = [i for i in rel if i["is_closed"] and i.get("status") in obsolete_status]
        if not closed:
            continue
        payload = [
            {
                "id": i["id"],
                "status": i["status"],
                "closed_on": i.get("closed_on"),
                "duplicate_of": duplicate_of(tracker, i["id"]) if i["status"] == "Duplicate" else [],
            }
            for i in closed
        ]
        out.append(
            {
                "number": r["number"],
                "tickets": info,
                "relevant": [i["id"] for i in rel],
                "closed": payload,
                "all_closed": len(closed) == len(rel) and all(i["is_closed"] for i in rel),
            }
        )
    return out
