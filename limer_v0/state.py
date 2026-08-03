"""Versioned route-plan transition state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from .route_plan import RoutePlan


@dataclass
class PreparedTransition:
    version: int
    plan: RoutePlan
    effective_round: int
    committed: bool = False


class RouteState:
    def __init__(self, initial_plan: RoutePlan) -> None:
        self.active_plan = initial_plan
        self.active_version = 0
        self.prepared: Optional[PreparedTransition] = None

    def prepare(
        self, version: int, plan: RoutePlan, effective_round: int
    ) -> None:
        if self.prepared is not None:
            raise ValueError("a route transition is already prepared")
        if version != self.active_version + 1:
            raise ValueError("prepared version must be the next version")
        if plan.world_size != self.active_plan.world_size:
            raise ValueError("prepared plan world_size must match the active plan")
        if plan.fingerprint == self.active_plan.fingerprint:
            raise ValueError("prepared plan must differ from the active plan")
        if effective_round < 0:
            raise ValueError("effective_round must be non-negative")
        self.prepared = PreparedTransition(version, plan, effective_round)

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

    def plan_for(self, round_id: int) -> Tuple[RoutePlan, int]:
        if round_id < 0:
            raise ValueError("round_id must be non-negative")
        if (
            self.prepared is not None
            and self.prepared.committed
            and round_id >= self.prepared.effective_round
        ):
            self.active_plan = self.prepared.plan
            self.active_version = self.prepared.version
            self.prepared = None
        return self.active_plan, self.active_version
