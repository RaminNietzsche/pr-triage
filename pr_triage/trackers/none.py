class NoneTracker:
    def issue(self, tid: str) -> dict:
        return {"id": int(tid), "status": "disabled", "is_closed": None}

    def duplicate_of(self, tid: str) -> list:
        return []
