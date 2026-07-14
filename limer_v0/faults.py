"""Runtime qdisc profile control."""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass, replace
from typing import Any, Callable, Dict, List, Optional

from .qdisc import PortSample, parse_tc_json


INTERFACE_PATTERN = re.compile(r"[A-Za-z0-9_.:-]+")
CommandRunner = Callable[[List[str]], subprocess.CompletedProcess[str]]
TextReader = Callable[[str], str]


@dataclass(frozen=True)
class TcProfile:
    rate_mbit: float
    delay_ms: float
    loss_pct: float = 0.0
    limit_packets: int = 1000

    def __post_init__(self) -> None:
        if self.rate_mbit <= 0:
            raise ValueError("rate_mbit must be positive")
        if self.delay_ms < 0:
            raise ValueError("delay_ms must be non-negative")
        if not 0 <= self.loss_pct < 100:
            raise ValueError("loss_pct must be in [0, 100)")
        if self.limit_packets <= 0:
            raise ValueError("limit_packets must be positive")


def _validate_interface(interface: str) -> None:
    if not INTERFACE_PATTERN.fullmatch(interface):
        raise ValueError(f"invalid interface name: {interface!r}")


def build_tc_command(interface: str, profile: TcProfile) -> List[str]:
    _validate_interface(interface)
    command = [
        "tc",
        "qdisc",
        "replace",
        "dev",
        interface,
        "root",
        "handle",
        "1:",
        "netem",
        "limit",
        str(profile.limit_packets),
        "delay",
        f"{profile.delay_ms}ms",
        "rate",
        f"{profile.rate_mbit}mbit",
    ]
    if profile.loss_pct:
        command.extend(["loss", f"{profile.loss_pct}%"])
    return command


def _default_run(command: List[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )


def _default_read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def read_operstate(
    interface: str, *, read_text: TextReader = _default_read_text
) -> str:
    _validate_interface(interface)
    path = f"/sys/class/net/{interface}/operstate"
    return read_text(path).strip()


def read_interface_counter(
    interface: str,
    counter: str,
    *,
    read_text: TextReader = _default_read_text,
) -> int:
    _validate_interface(interface)
    if counter not in {
        "rx_bytes",
        "rx_packets",
        "rx_dropped",
        "tx_bytes",
        "tx_packets",
        "tx_dropped",
    }:
        raise ValueError(f"unsupported interface counter: {counter!r}")
    path = f"/sys/class/net/{interface}/statistics/{counter}"
    return int(read_text(path).strip())


def sample_qdisc(
    interface: str,
    t_ns: Optional[int] = None,
    *,
    run_command: CommandRunner = _default_run,
    read_text: TextReader = _default_read_text,
) -> PortSample:
    _validate_interface(interface)
    completed = run_command(
        ["tc", "-s", "-j", "qdisc", "show", "dev", interface]
    )
    sample = parse_tc_json(
        completed.stdout,
        interface,
        time.monotonic_ns() if t_ns is None else t_ns,
    )
    return replace(
        sample,
        rx_bytes=read_interface_counter(
            interface, "rx_bytes", read_text=read_text
        ),
        rx_packets=read_interface_counter(
            interface, "rx_packets", read_text=read_text
        ),
        rx_dropped=read_interface_counter(
            interface, "rx_dropped", read_text=read_text
        ),
        tx_bytes=read_interface_counter(
            interface, "tx_bytes", read_text=read_text
        ),
        tx_packets=read_interface_counter(
            interface, "tx_packets", read_text=read_text
        ),
        tx_dropped=read_interface_counter(
            interface, "tx_dropped", read_text=read_text
        ),
    )


def apply_profile(
    interface: str,
    profile: TcProfile,
    *,
    run_command: CommandRunner = _default_run,
    read_text: TextReader = _default_read_text,
) -> Dict[str, Any]:
    command = build_tc_command(interface, profile)
    t_before_ns = time.monotonic_ns()
    run_command(command)
    t_after_ns = time.monotonic_ns()
    sample = sample_qdisc(
        interface,
        t_after_ns,
        run_command=run_command,
        read_text=read_text,
    )
    return {
        "interface": interface,
        "command": command,
        "t_before_ns": t_before_ns,
        "t_after_ns": t_after_ns,
        "operstate": read_operstate(interface, read_text=read_text),
        "sample": sample.to_dict(),
        "profile": {
            "rate_mbit": profile.rate_mbit,
            "delay_ms": profile.delay_ms,
            "loss_pct": profile.loss_pct,
            "limit_packets": profile.limit_packets,
        },
    }
