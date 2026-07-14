"""Framed transport primitives for the AllReduce-like workload."""

from __future__ import annotations

import socket
import struct
import zlib
from dataclasses import dataclass
from typing import Tuple


MAGIC = b"LMR0"
UINT32_MAX = (1 << 32) - 1
HEADER_STRUCT = struct.Struct("!4sIIIII")
HEADER_SIZE = HEADER_STRUCT.size


@dataclass(frozen=True)
class FrameHeader:
    round_id: int
    step_id: int
    version: int
    payload_len: int
    checksum: int

    def pack(self) -> bytes:
        values = {
            "round_id": self.round_id,
            "step_id": self.step_id,
            "version": self.version,
            "payload_len": self.payload_len,
            "checksum": self.checksum,
        }
        for name, value in values.items():
            if not isinstance(value, int) or not 0 <= value <= UINT32_MAX:
                raise ValueError(f"{name} must be an unsigned 32-bit integer")
        return HEADER_STRUCT.pack(
            MAGIC,
            self.round_id,
            self.step_id,
            self.version,
            self.payload_len,
            self.checksum,
        )

    @classmethod
    def unpack(cls, data: bytes) -> "FrameHeader":
        if len(data) != HEADER_SIZE:
            raise ValueError(f"header must be exactly {HEADER_SIZE} bytes")
        magic, round_id, step_id, version, payload_len, checksum = HEADER_STRUCT.unpack(data)
        if magic != MAGIC:
            raise ValueError(f"invalid frame magic: {magic!r}")
        return cls(round_id, step_id, version, payload_len, checksum)


def crc32(data: bytes) -> int:
    return zlib.crc32(data) & UINT32_MAX


def recv_exact(sock: socket.socket, size: int) -> bytes:
    if size < 0:
        raise ValueError("size must be non-negative")
    chunks = bytearray()
    while len(chunks) < size:
        chunk = sock.recv(size - len(chunks))
        if not chunk:
            raise EOFError(f"expected {size} bytes, received {len(chunks)}")
        chunks.extend(chunk)
    return bytes(chunks)


def send_frame(sock: socket.socket, header: FrameHeader, payload: bytes) -> None:
    if len(payload) != header.payload_len:
        raise ValueError("payload length does not match frame header")
    if crc32(payload) != header.checksum:
        raise ValueError("payload checksum does not match frame header")
    sock.sendall(header.pack())
    sock.sendall(payload)


def recv_frame(sock: socket.socket) -> Tuple[FrameHeader, bytes]:
    header = FrameHeader.unpack(recv_exact(sock, HEADER_SIZE))
    payload = recv_exact(sock, header.payload_len)
    if crc32(payload) != header.checksum:
        raise ValueError("received payload checksum mismatch")
    return header, payload
