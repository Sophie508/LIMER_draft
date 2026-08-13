"""Event-driven link-state watch for hard port failures.

Polling counters every 20 ms bounds detection at tens of milliseconds; a hard
link failure is instead surfaced by the kernel as a netlink RTM_NEWLINK
notification the moment the carrier drops, so subscribing to RTNLGRP_LINK
gives sub-millisecond, interrupt-style detection — the emulation analog of a
switch port-down interrupt. The watcher runs beside the counter sampler: the
sampler still covers gray degradation, this path covers hard failures.

The message parser is a pure function over raw netlink bytes so it is unit
testable off-Linux; only the socket loop needs AF_NETLINK.
"""

from __future__ import annotations

import socket
import struct
import threading
import time
from typing import Any, Callable, Dict, List, Optional


RTM_NEWLINK = 16
RTM_DELLINK = 17
RTNLGRP_LINK = 1
IFF_LOWER_UP = 1 << 16
IFF_RUNNING = 1 << 6
IFLA_OPERSTATE = 16
NLMSG_HDR = struct.Struct("=IHHII")
IFINFOMSG = struct.Struct("=BBHiII")
RTATTR_HDR = struct.Struct("=HH")
OPERSTATE_NAMES = {
    0: "unknown",
    1: "notpresent",
    2: "down",
    3: "lowerlayerdown",
    4: "testing",
    5: "dormant",
    6: "up",
}
DOWN_OPERSTATES = {"down", "lowerlayerdown", "notpresent"}


def _align4(value: int) -> int:
    return (value + 3) & ~3


def parse_link_messages(data: bytes) -> List[Dict[str, Any]]:
    """Parse a netlink datagram into link-state records."""
    records: List[Dict[str, Any]] = []
    offset = 0
    while offset + NLMSG_HDR.size <= len(data):
        msg_len, msg_type, _flags, _seq, _pid = NLMSG_HDR.unpack_from(data, offset)
        if msg_len < NLMSG_HDR.size or offset + msg_len > len(data):
            break
        if msg_type in (RTM_NEWLINK, RTM_DELLINK):
            body = offset + NLMSG_HDR.size
            if body + IFINFOMSG.size <= offset + msg_len:
                _family, _pad, _dev_type, index, flags, _change = IFINFOMSG.unpack_from(
                    data, body
                )
                operstate: Optional[str] = None
                attr_offset = body + IFINFOMSG.size
                end = offset + msg_len
                while attr_offset + RTATTR_HDR.size <= end:
                    attr_len, attr_type = RTATTR_HDR.unpack_from(data, attr_offset)
                    if attr_len < RTATTR_HDR.size:
                        break
                    if attr_type == IFLA_OPERSTATE and attr_offset + attr_len <= end:
                        operstate = OPERSTATE_NAMES.get(
                            data[attr_offset + RTATTR_HDR.size], "unknown"
                        )
                    attr_offset += _align4(attr_len)
                lower_up = bool(flags & IFF_LOWER_UP)
                running = bool(flags & IFF_RUNNING)
                records.append(
                    {
                        "ifindex": index,
                        "deleted": msg_type == RTM_DELLINK,
                        "flags": flags,
                        "lower_up": lower_up,
                        "running": running,
                        "operstate": operstate,
                        "link_down": (
                            msg_type == RTM_DELLINK
                            or not lower_up
                            or not running
                            or (operstate in DOWN_OPERSTATES)
                        ),
                    }
                )
        offset += _align4(msg_len)
    return records


class LinkEventMonitor:
    """Subscribe to kernel link notifications for one interface.

    Fires the callback exactly once, on the first down transition of the
    watched interface, with a monotonic timestamp taken as early as possible
    after the datagram is received so the measured latency charges everything
    downstream of the kernel notification to this management-plane process.
    """

    rule_version = "l1-v0.4-netlink-linkdown"

    def __init__(
        self,
        interface: str,
        on_down: Callable[[Dict[str, Any]], None],
    ) -> None:
        self.interface = interface
        self.on_down = on_down
        self._ifindex = socket.if_nametoindex(interface)
        self._sock = socket.socket(
            socket.AF_NETLINK, socket.SOCK_RAW, socket.NETLINK_ROUTE
        )
        self._sock.bind((0, 1 << (RTNLGRP_LINK - 1)))
        self._sock.settimeout(0.5)
        self._fired = False
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set() and not self._fired:
            try:
                data = self._sock.recv(65536)
            except socket.timeout:
                continue
            except OSError:
                return
            received_t_ns = time.monotonic_ns()
            for record in parse_link_messages(data):
                if record["ifindex"] != self._ifindex or not record["link_down"]:
                    continue
                if self._fired:
                    break
                self._fired = True
                event = dict(record)
                event["interface"] = self.interface
                event["t_monotonic_ns"] = received_t_ns
                event["rule_version"] = self.rule_version
                self.on_down(event)
                break

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2.0)
        try:
            self._sock.close()
        except OSError:
            pass
