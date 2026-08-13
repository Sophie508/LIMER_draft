"""Immutable sender-by-step routing plans for the LIMER prototype."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Dict, List, Mapping, Sequence, Tuple


SUPPORTED_FABRICS = frozenset({"A", "B"})
PLAN_KEYS = frozenset({"world_size", "policy", "routes"})


@dataclass(frozen=True)
class RoutePlan:
    """A complete immutable route choice for every sender and ring step."""

    world_size: int
    policy: str
    routes: Tuple[Tuple[str, ...], ...]

    def __post_init__(self) -> None:
        if isinstance(self.world_size, bool) or not isinstance(self.world_size, int):
            raise ValueError("world_size must be an integer")
        if self.world_size < 2:
            raise ValueError("world_size must be at least two")
        if not isinstance(self.policy, str) or not self.policy.strip():
            raise ValueError("policy must be a non-empty string")

        try:
            normalized = tuple(tuple(str(route) for route in row) for row in self.routes)
        except TypeError as exc:
            raise ValueError("routes must be a sequence of sender rows") from exc
        object.__setattr__(self, "policy", self.policy.strip())
        object.__setattr__(self, "routes", normalized)

        if len(normalized) != self.world_size:
            raise ValueError(
                f"route plan must contain exactly {self.world_size} sender rows"
            )
        for rank, row in enumerate(normalized):
            if len(row) != self.steps:
                raise ValueError(
                    f"sender row {rank} must contain exactly {self.steps} steps"
                )
            unsupported = sorted(set(row) - SUPPORTED_FABRICS)
            if unsupported:
                raise ValueError(
                    "route plan contains unsupported fabric values: "
                    + ", ".join(unsupported)
                )

    @property
    def steps(self) -> int:
        return 2 * (self.world_size - 1)

    @classmethod
    def single_fabric(cls, world_size: int, route: str = "A") -> "RoutePlan":
        cls._validate_fabric(route)
        steps = 2 * (world_size - 1)
        routes = tuple(tuple(route for _ in range(steps)) for _ in range(world_size))
        return cls(world_size, f"single_fabric_{route}", routes)

    @classmethod
    def balanced_active_active(cls, world_size: int) -> "RoutePlan":
        steps = 2 * (world_size - 1)
        routes = tuple(
            tuple(
                "A" if (rank + step) % 2 == 0 else "B"
                for step in range(steps)
            )
            for rank in range(world_size)
        )
        return cls(world_size, "balanced_active_active", routes)

    @classmethod
    def global_fabric(cls, world_size: int, route: str) -> "RoutePlan":
        cls._validate_fabric(route)
        steps = 2 * (world_size - 1)
        routes = tuple(tuple(route for _ in range(steps)) for _ in range(world_size))
        return cls(world_size, f"global_fabric_{route}", routes)

    @staticmethod
    def _validate_fabric(route: str) -> None:
        if route not in SUPPORTED_FABRICS:
            raise ValueError("fabric must be A or B")

    def route_for(self, sender_rank: int, step_id: int) -> str:
        if not 0 <= sender_rank < self.world_size:
            raise IndexError("sender_rank is out of range")
        if not 0 <= step_id < self.steps:
            raise IndexError("step_id is out of range")
        return self.routes[sender_rank][step_id]

    def localized_reroute(
        self, sender_rank: int, failed_route: str, alternate_route: str
    ) -> "RoutePlan":
        if not 0 <= sender_rank < self.world_size:
            raise IndexError("sender_rank is out of range")
        self._validate_fabric(failed_route)
        self._validate_fabric(alternate_route)
        if failed_route == alternate_route:
            raise ValueError("failed and alternate routes must be different")

        routes: List[List[str]] = [list(row) for row in self.routes]
        changed = 0
        for step_id, route in enumerate(routes[sender_rank]):
            if route == failed_route:
                routes[sender_rank][step_id] = alternate_route
                changed += 1
        if changed == 0:
            raise ValueError("localized reroute found no slots on the failed route")
        return RoutePlan(
            self.world_size,
            "localized_reroute",
            tuple(tuple(row) for row in routes),
        )

    def localized_link_reroute(
        self, affected_rank: int, failed_route: str, alternate_route: str
    ) -> "RoutePlan":
        """Reroute every slot that traverses one worker's access link.

        A hard (bidirectional) failure of the link between affected_rank and
        one fabric kills both that worker's sends on the fabric and the sends
        of its ring predecessor addressed to it. The minimal repair therefore
        moves exactly two senders' failed-route slots: the affected rank's own,
        and its predecessor's. Contrast with localized_reroute, which models a
        directed egress-only impairment and moves one sender's slots.
        """
        if not 0 <= affected_rank < self.world_size:
            raise IndexError("affected_rank is out of range")
        self._validate_fabric(failed_route)
        self._validate_fabric(alternate_route)
        if failed_route == alternate_route:
            raise ValueError("failed and alternate routes must be different")
        predecessor = (affected_rank - 1) % self.world_size
        routes: List[List[str]] = [list(row) for row in self.routes]
        changed = 0
        for sender_rank in (affected_rank, predecessor):
            for step_id, route in enumerate(routes[sender_rank]):
                if route == failed_route:
                    routes[sender_rank][step_id] = alternate_route
                    changed += 1
        if changed == 0:
            raise ValueError("link reroute found no slots on the failed route")
        return RoutePlan(
            self.world_size,
            "localized_link_reroute",
            tuple(tuple(row) for row in routes),
        )

    def changed_slots(self, target: "RoutePlan") -> List[Dict[str, Any]]:
        if self.world_size != target.world_size:
            raise ValueError("route plans must have the same world_size")
        changes: List[Dict[str, Any]] = []
        for sender_rank in range(self.world_size):
            for step_id in range(self.steps):
                old_route = self.route_for(sender_rank, step_id)
                new_route = target.route_for(sender_rank, step_id)
                if old_route != new_route:
                    changes.append(
                        {
                            "sender_rank": sender_rank,
                            "step_id": step_id,
                            "old_route": old_route,
                            "new_route": new_route,
                        }
                    )
        return changes

    def to_dict(self) -> Dict[str, Any]:
        return {
            "world_size": self.world_size,
            "policy": self.policy,
            "routes": [list(row) for row in self.routes],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RoutePlan":
        keys = set(value)
        if keys != PLAN_KEYS:
            missing = sorted(PLAN_KEYS - keys)
            extra = sorted(keys - PLAN_KEYS)
            raise ValueError(
                f"route plan keys do not match schema; missing={missing}, extra={extra}"
            )
        routes = value["routes"]
        if not isinstance(routes, Sequence) or isinstance(routes, (str, bytes)):
            raise ValueError("routes must be a sequence of sender rows")
        normalized_rows = []
        for row in routes:
            if not isinstance(row, Sequence) or isinstance(row, (str, bytes)):
                raise ValueError("each route row must be a sequence")
            normalized_rows.append(tuple(str(route) for route in row))
        return cls(
            int(value["world_size"]),
            str(value["policy"]),
            tuple(normalized_rows),
        )

    def canonical_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()
