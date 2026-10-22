"""Experimental passive host loss confirmation; never reads injector state.

Offsets use Linux v6.8 include/uapi/linux/tcp.h (native UAPI layout).
RACK/DSACK motivates the feedback veto; this does not implement RACK or
prove a physical failure cause. tcp-loss-v1 must be validated independently.
"""
from __future__ import annotations

from collections import deque
import socket
import struct
import sys
import time
from typing import Mapping, Optional


TCP_DELIVERY_PREFIX_BYTES = 224
RULE_VERSION = "tcp-loss-v3"


def parse_delivery_info(info: bytes) -> dict:
    if len(info) < TCP_DELIVERY_PREFIX_BYTES:
        raise ValueError("extended TCP_INFO prefix is shorter than 224 bytes")
    fields = {"unacked": 24, "lost": 32, "retrans": 36, "rtt_us": 68,
              "total_retrans": 100, "dsack_dups": 216, "reord_seen": 220}
    result = {name: struct.unpack_from("=I", info, offset)[0]
              for name, offset in fields.items()}
    result.update(ca_state=info[1],
                  bytes_acked=struct.unpack_from("=Q", info, 120)[0],
                  bytes_sent=struct.unpack_from("=Q", info, 200)[0],
                  bytes_retrans=struct.unpack_from("=Q", info, 208)[0])
    return result


class TcpDeliverySampler:
    """Bracket reads separately and identify replacement connections."""

    def __init__(self) -> None:
        self._connections = {}
        self._generation = 0

    def sample(self, sockets: Mapping[str, socket.socket]) -> list:
        rows = []
        for fabric, sock in sorted(sockets.items()):
            previous = self._connections.get(fabric)
            if previous is None or previous[0] is not sock:
                self._generation += 1
                self._connections[fabric] = (sock, self._generation)
            row = dict(fabric=fabric,
                       connection_generation=self._connections[fabric][1],
                       read_start_ns=time.monotonic_ns())
            try:
                if sys.platform != "linux" or not hasattr(socket, "TCP_INFO"):
                    raise OSError("extended Linux TCP_INFO is unavailable")
                info = sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_INFO,
                                      TCP_DELIVERY_PREFIX_BYTES)
                row.update(parse_delivery_info(info), status="ok", abi_bytes=len(info))
            except (OSError, ValueError) as exc:
                row.update(status="unavailable", error_type=type(exc).__name__,
                           error=str(exc))
            row["sample_t_monotonic_ns"] = time.monotonic_ns()
            row["read_duration_ns"] = row["sample_t_monotonic_ns"] - row["read_start_ns"]
            rows.append(row)
        for fabric in set(self._connections) - set(sockets):
            del self._connections[fabric]
        return rows


class TcpLossDetector:
    """One connection's prospective rule, independent of fault timing/location.

    A decision concerns persistent TCP delivery loss, not its physical cause.
    Delays longer than the hold time can still cause false confirmation.
    """

    HOLD_NS = 30_000_000
    WINDOW_NS = 100_000_000
    MAX_SAMPLE_GAP_NS = 15_000_000
    MIN_RETRANSMISSIONS = 2
    COUNTERS = ("total_retrans", "dsack_dups", "reord_seen")

    def __init__(self) -> None:
        self._previous: Optional[dict] = None
        self._retransmissions = deque()
        self._candidate_ns: Optional[int] = None
        self._veto_until_ns = 0
        self._confirmed_generation = None
        self._active_generation = None

    def _clear_evidence(self) -> None:
        self._retransmissions.clear()
        self._candidate_ns = None

    def observe(self, sample: Mapping) -> Optional[dict]:
        required = ("connection_generation", "sample_t_monotonic_ns",
                    "lost", "unacked") + self.COUNTERS
        if sample.get("status") != "ok" or any(sample.get(k) is None for k in required):
            self._previous = None
            self._clear_evidence()
            return None
        row = dict(sample)
        previous, self._previous = self._previous, row
        now = int(row["sample_t_monotonic_ns"])
        generation = row["connection_generation"]
        if generation != self._active_generation:
            self._active_generation = generation
            self._veto_until_ns = 0
            self._clear_evidence()
        replacement = previous is None or previous["connection_generation"] != generation
        if replacement:
            self._clear_evidence()
            # Missing reads on the same generation must not erase a recent veto.
            if previous is not None and previous["connection_generation"] != generation:
                self._veto_until_ns = 0
            return None
        dt = now - int(previous["sample_t_monotonic_ns"])
        if dt <= 0 or dt > self.MAX_SAMPLE_GAP_NS or any(
                int(row[k]) < int(previous[k]) for k in self.COUNTERS):
            self._clear_evidence()
            return None
        if any(int(row[k]) > int(previous[k]) for k in ("dsack_dups", "reord_seen")):
            self._veto_until_ns = now + self.WINDOW_NS
            self._clear_evidence()
            return None
        if now < self._veto_until_ns or generation == self._confirmed_generation:
            self._clear_evidence()
            return None
        delta = int(row["total_retrans"]) - int(previous["total_retrans"])
        if delta:
            self._retransmissions.append((now, delta))
        while self._retransmissions and self._retransmissions[0][0] < now - self.WINDOW_NS:
            self._retransmissions.popleft()
        if int(row["unacked"]) <= 0 or not self._retransmissions:
            self._candidate_ns = None
            return None
        if self._candidate_ns is None:
            if int(row["lost"]) <= 0:
                return None
            self._candidate_ns = now
        count = sum(delta for _, delta in self._retransmissions)
        age = now - self._candidate_ns
        if age < self.HOLD_NS or count < self.MIN_RETRANSMISSIONS:
            return None
        self._confirmed_generation = generation
        return dict(rule_version=RULE_VERSION, action="confirm_delivery_loss",
                    connection_generation=generation, candidate_t_ns=self._candidate_ns,
                    decision_t_monotonic_ns=now, evidence_age_ms=age / 1e6,
                    retransmissions_in_window=count, hold_ms=self.HOLD_NS / 1e6,
                    feedback_veto_ms=self.WINDOW_NS / 1e6,
                    claim_boundary="Experimental host decision; cause and accuracy unvalidated",
                    evidence={k: row[k] for k in required})
