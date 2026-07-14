"""Linux tc qdisc parsing helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class PortSample:
    interface: str
    t_ns: int
    kind: str
    bytes: int
    packets: int
    drops: int
    overlimits: int
    requeues: int
    backlog_bytes: int
    qlen: int
    rx_bytes: int = 0
    rx_packets: int = 0
    rx_dropped: int = 0
    tx_bytes: int = 0
    tx_packets: int = 0
    tx_dropped: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "interface": self.interface,
            "t_ns": self.t_ns,
            "kind": self.kind,
            "bytes": self.bytes,
            "packets": self.packets,
            "drops": self.drops,
            "overlimits": self.overlimits,
            "requeues": self.requeues,
            "backlog_bytes": self.backlog_bytes,
            "qlen": self.qlen,
            "rx_bytes": self.rx_bytes,
            "rx_packets": self.rx_packets,
            "rx_dropped": self.rx_dropped,
            "tx_bytes": self.tx_bytes,
            "tx_packets": self.tx_packets,
            "tx_dropped": self.tx_dropped,
        }


def _counter(item: Dict[str, Any], name: str) -> int:
    value = item.get(name, 0)
    if isinstance(value, dict):
        value = value.get("bytes", value.get("value", 0))
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid qdisc counter {name}: {value!r}") from exc


def parse_tc_json(text: str, interface: str, t_ns: int) -> PortSample:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid tc JSON") from exc
    if not isinstance(data, list) or not data:
        raise ValueError(f"no qdisc entry for interface {interface}")
    roots = [item for item in data if isinstance(item, dict) and item.get("root")]
    item = roots[0] if roots else data[0]
    if not isinstance(item, dict):
        raise ValueError(f"no qdisc object for interface {interface}")
    return PortSample(
        interface=interface,
        t_ns=int(t_ns),
        kind=str(item.get("kind", "unknown")),
        bytes=_counter(item, "bytes"),
        packets=_counter(item, "packets"),
        drops=_counter(item, "drops"),
        overlimits=_counter(item, "overlimits"),
        requeues=_counter(item, "requeues"),
        backlog_bytes=_counter(item, "backlog"),
        qlen=_counter(item, "qlen"),
    )
