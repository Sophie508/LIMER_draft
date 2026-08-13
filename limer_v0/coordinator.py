"""Versioned all-rank route-plan coordination for the LIMER prototype."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from .route_plan import RoutePlan


@dataclass(frozen=True)
class TransitionProposal:
    version: int
    plan: RoutePlan
    effective_round: int
    current_round: int
    changed_slots: List[Dict[str, Any]]
    effective_step: int = 0

    @property
    def plan_fingerprint(self) -> str:
        return self.plan.fingerprint

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "plan": self.plan.to_dict(),
            "plan_fingerprint": self.plan_fingerprint,
            "policy": self.plan.policy,
            "effective_round": self.effective_round,
            "effective_step": self.effective_step,
            "current_round": self.current_round,
            "changed_slots": list(self.changed_slots),
        }


@dataclass(frozen=True)
class TransitionDecision:
    action: str
    version: int
    plan: RoutePlan
    effective_round: int
    ready_ranks: List[int]
    missing_ranks: List[int]
    changed_slots: List[Dict[str, Any]]
    effective_step: int = 0

    @property
    def plan_fingerprint(self) -> str:
        return self.plan.fingerprint

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "version": self.version,
            "plan": self.plan.to_dict(),
            "plan_fingerprint": self.plan_fingerprint,
            "policy": self.plan.policy,
            "effective_round": self.effective_round,
            "effective_step": self.effective_step,
            "ready_ranks": list(self.ready_ranks),
            "missing_ranks": list(self.missing_ranks),
            "changed_slots": list(self.changed_slots),
        }


class RecoveryCoordinator:
    def __init__(self, initial_plan: RoutePlan) -> None:
        self.world_size = initial_plan.world_size
        self.active_version = 0
        self.active_plan = initial_plan
        self.pending: Optional[TransitionProposal] = None
        self._ready: Set[int] = set()

    def propose(
        self,
        plan: RoutePlan,
        effective_round: int,
        current_round: int,
        effective_step: int = 0,
        allow_current_round: bool = False,
    ) -> TransitionProposal:
        if self.pending is not None:
            raise ValueError("a transition is already pending")
        if plan.world_size != self.world_size:
            raise ValueError("proposal plan world_size does not match the coordinator")
        if plan.fingerprint == self.active_plan.fingerprint:
            raise ValueError("proposal plan must differ from the active plan")
        if not 0 <= effective_step < plan.steps:
            raise ValueError("effective_step must be a valid step index")
        if effective_step == 0 and not allow_current_round:
            # A round-boundary cutover must land on a future round.
            if effective_round <= current_round:
                raise ValueError("effective round must be in the future")
        elif effective_round < current_round:
            # A mid-round cutover may target the round in flight, including
            # its very first step when the fault lands before any step
            # completes (allow_current_round).
            raise ValueError("effective round must not be in the past")
        self.pending = TransitionProposal(
            version=self.active_version + 1,
            plan=plan,
            effective_round=effective_round,
            current_round=current_round,
            changed_slots=self.active_plan.changed_slots(plan),
            effective_step=effective_step,
        )
        self._ready.clear()
        return self.pending

    def record_ready(
        self, rank: int, version: int, plan_fingerprint: str
    ) -> None:
        if self.pending is None:
            raise ValueError("no pending proposal")
        if version != self.pending.version:
            raise ValueError("READY version does not match the pending version")
        if plan_fingerprint != self.pending.plan_fingerprint:
            raise ValueError("READY fingerprint does not match the pending plan")
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
            plan=proposal.plan,
            effective_round=proposal.effective_round,
            ready_ranks=ready,
            missing_ranks=missing,
            changed_slots=proposal.changed_slots,
            effective_step=proposal.effective_step,
        )
        if action == "commit":
            self.active_version = proposal.version
            self.active_plan = proposal.plan
        self.pending = None
        self._ready.clear()
        return decision
