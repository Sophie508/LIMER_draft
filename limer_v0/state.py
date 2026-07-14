"""Versioned route transition state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class PreparedTransition:
    version: int
    route: str
    effective_round: int
    committed: bool = False


class RouteState:
    def __init__(self) -> None:
        self.active_route = "A"
        self.active_version = 0
        self.prepared: Optional[PreparedTransition] = None

    def prepare(self, version: int, route: str, effective_round: int) -> None:
        if self.prepared is not None:
            raise ValueError("a route transition is already prepared")
        if version != self.active_version + 1:
            raise ValueError("prepared version must be the next version")
        if route not in {"A", "B"}:
            raise ValueError("route must be A or B")
        if route == self.active_route:
            raise ValueError("prepared route must differ from active route")
        if effective_round < 0:
            raise ValueError("effective_round must be non-negative")
        self.prepared = PreparedTransition(version, route, effective_round)

    def commit(self, version: int) -> None:
        if self.prepared is None:
            raise ValueError("no prepared transition to commit")
        if version != self.prepared.version:
            raise ValueError("commit version does not match prepared version")
        self.prepared.committed = True

    def abort(self, version: int) -> None:
        if self.prepared is None:
            raise ValueError("no prepared transition to abort")
        if version != self.prepared.version:
            raise ValueError("abort version does not match prepared version")
        self.prepared = None

    def route_for(self, round_id: int) -> Tuple[str, int]:
        if round_id < 0:
            raise ValueError("round_id must be non-negative")
        if (
            self.prepared is not None
            and self.prepared.committed
            and round_id >= self.prepared.effective_round
        ):
            self.active_route = self.prepared.route
            self.active_version = self.prepared.version
            self.prepared = None
        return self.active_route, self.active_version
