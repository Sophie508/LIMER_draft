"""Versioned all-rank recovery coordination for LIMER CPU v0."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Set


@dataclass(frozen=True)
class TransitionProposal:
    version: int
    route: str
    effective_round: int
    current_round: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TransitionDecision:
    action: str
    version: int
    route: str
    effective_round: int
    ready_ranks: List[int]
    missing_ranks: List[int]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RecoveryCoordinator:
    def __init__(self, world_size: int) -> None:
        if world_size < 2:
            raise ValueError("world_size must be at least two")
        self.world_size = world_size
        self.active_version = 0
        self.active_route = "A"
        self.pending: Optional[TransitionProposal] = None
        self._ready: Set[int] = set()

    def propose(
        self, route: str, effective_round: int, current_round: int
    ) -> TransitionProposal:
        if self.pending is not None:
            raise ValueError("a transition is already pending")
        if route not in {"A", "B"}:
            raise ValueError("route must be A or B")
        if route == self.active_route:
            raise ValueError("proposal route must differ from active route")
        if effective_round <= current_round:
            raise ValueError("effective round must be in the future")
        self.pending = TransitionProposal(
            version=self.active_version + 1,
            route=route,
            effective_round=effective_round,
            current_round=current_round,
        )
        self._ready.clear()
        return self.pending

    def record_ready(self, rank: int, version: int) -> None:
        if self.pending is None:
            raise ValueError("no pending proposal")
        if version != self.pending.version:
            raise ValueError("READY version does not match the pending version")
        if not 0 <= rank < self.world_size:
            raise ValueError("READY rank is out of range")
        if rank in self._ready:
            raise ValueError(f"duplicate READY from rank {rank}")
        self._ready.add(rank)

    def commit_or_abort(self) -> TransitionDecision:
        if self.pending is None:
            raise ValueError("no pending proposal")
        proposal = self.pending
        ready = sorted(self._ready)
        missing = sorted(set(range(self.world_size)) - self._ready)
        action = "commit" if not missing else "abort"
        decision = TransitionDecision(
            action=action,
            version=proposal.version,
            route=proposal.route,
            effective_round=proposal.effective_round,
            ready_ranks=ready,
            missing_ranks=missing,
        )
        if action == "commit":
            self.active_version = proposal.version
            self.active_route = proposal.route
        self.pending = None
        self._ready.clear()
        return decision
