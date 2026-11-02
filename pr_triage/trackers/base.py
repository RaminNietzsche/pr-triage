from typing import Protocol


class TrackerAdapter(Protocol):
    def issue(self, tid: str) -> dict: ...

    def duplicate_of(self, tid: str) -> list: ...
