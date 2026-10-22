"""Observation-only Linux TCP retransmission telemetry.

The Linux UAPI tcp_info prefix contains tcpi_total_retrans at byte 100.
Source: https://github.com/torvalds/linux/blob/master/include/uapi/linux/tcp.h
No fault injector state is read and no recovery decision is made here.
"""

from __future__ import annotations

import socket
import struct
import sys
from typing import Dict, Mapping


TCP_INFO_PREFIX_BYTES = 104
TOTAL_RETRANS_OFFSET = 100


def parse_total_retransmissions(info: bytes) -> int:
    if len(info) < TCP_INFO_PREFIX_BYTES:
        raise ValueError("TCP_INFO prefix is shorter than 104 bytes")
    return struct.unpack_from("=I", info, TOTAL_RETRANS_OFFSET)[0]


def read_total_retransmissions(sock: socket.socket) -> int:
    if sys.platform != "linux" or not hasattr(socket, "TCP_INFO"):
        raise OSError("Linux TCP_INFO telemetry is unavailable on this platform")
    return parse_total_retransmissions(
        sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_INFO, TCP_INFO_PREFIX_BYTES)
    )


class TcpRetransmissionSampler:
    """Keep connection-scoped cumulative counters, including failed reads."""

    def __init__(self) -> None:
        self._previous: Dict[str, tuple] = {}

    def sample(self, sockets: Mapping[str, socket.socket], t_ns: int) -> list:
        records = []
        for name, sock in sorted(sockets.items()):
            record = {"fabric": name, "sample_t_monotonic_ns": t_ns}
            try:
                total = read_total_retransmissions(sock)
            except (OSError, ValueError) as exc:
                self._previous.pop(name, None)
                record.update(status="unavailable", error_type=type(exc).__name__,
                              error=str(exc), total_retrans=None, retrans_delta=None,
                              sample_interval_ns=None)
            else:
                previous = self._previous.get(name)
                same_connection = previous is not None and previous[0] is sock
                record.update(
                    status="ok", total_retrans=total,
                    retrans_delta=((total - previous[1]) % (1 << 32)
                                   if same_connection else None),
                    sample_interval_ns=(t_ns - previous[2]
                                        if same_connection else None),
                )
                self._previous[name] = (sock, total, t_ns)
            records.append(record)
        for name in set(self._previous) - set(sockets):
            del self._previous[name]
        return records
