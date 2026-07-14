"""Mininet topologies for LIMER CPU v0."""

from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .faults import TcProfile, apply_profile, read_operstate


WORLD_SIZE = 4
FABRIC_PORTS = {"A": 15000, "B": 15001}
BASE_PROFILE = TcProfile(rate_mbit=100.0, delay_ms=1.0, loss_pct=0.0)


@dataclass(frozen=True)
class WorkerFabric:
    name: str
    local_ip: str
    next_ip: str
    port: int
    host_interface: str
    switch_interface: str

    def worker_argument(self) -> str:
        return f"{self.name},{self.local_ip},{self.next_ip},{self.port}"


@dataclass
class TopologyDescriptor:
    kind: str
    net: Any
    hosts: Dict[int, Any]
    fabrics: Dict[str, Dict[int, WorkerFabric]]
    profile_records: List[Dict[str, Any]]

    def fault_interface(self, route: str = "A", rank: int = 2) -> str:
        """Return the hidden injector interface on the worker side of the link."""
        return self.fabrics[route][rank].host_interface

    def detector_interface(self, route: str = "A", rank: int = 2) -> str:
        """Return the independently observed switch-facing peer interface."""
        return self.fabrics[route][rank].switch_interface

    def _host_command_runner(self, rank: int):
        host = self.hosts[rank]

        def run(command: List[str]) -> subprocess.CompletedProcess[str]:
            stdout, stderr, exit_code = host.pexec(*command)
            completed = subprocess.CompletedProcess(
                command,
                int(exit_code),
                str(stdout),
                str(stderr),
            )
            if completed.returncode != 0:
                raise subprocess.CalledProcessError(
                    completed.returncode,
                    command,
                    output=completed.stdout,
                    stderr=completed.stderr,
                )
            return completed

        return run

    def _host_text_reader(self, rank: int):
        run = self._host_command_runner(rank)

        def read_text(path: str) -> str:
            return run(["cat", path]).stdout

        return read_text

    def apply_fault_profile(
        self,
        profile: TcProfile,
        route: str = "A",
        rank: int = 2,
    ) -> Dict[str, Any]:
        """Apply the hidden qdisc inside the selected worker namespace."""
        return apply_profile(
            self.fault_interface(route, rank),
            profile,
            run_command=self._host_command_runner(rank),
            read_text=self._host_text_reader(rank),
        )

    def fault_operstate(self, route: str = "A", rank: int = 2) -> str:
        """Read host-interface state from the worker namespace."""
        return read_operstate(
            self.fault_interface(route, rank),
            read_text=self._host_text_reader(rank),
        )

    def ping_fabric(self, route: str) -> Dict[str, Any]:
        if route not in self.fabrics:
            raise ValueError(f"unknown fabric: {route}")
        records: List[Dict[str, Any]] = []
        endpoints = self.fabrics[route]
        for rank in range(WORLD_SIZE):
            endpoint = endpoints[rank]
            output = self.hosts[rank].cmd(
                "ping",
                "-c",
                "1",
                "-W",
                "2",
                "-I",
                endpoint.local_ip,
                endpoint.next_ip,
            )
            success = "1 received" in output or "1 packets received" in output
            latency_match = re.search(r"time[=<]([0-9.]+)\s*ms", output)
            latency_ms = float(latency_match.group(1)) if latency_match else None
            records.append(
                {
                    "route": route,
                    "rank": rank,
                    "source": endpoint.local_ip,
                    "destination": endpoint.next_ip,
                    "success": success,
                    "latency_ms": latency_ms,
                    "output": output.strip(),
                }
            )
        latencies = [
            float(record["latency_ms"])
            for record in records
            if record["latency_ms"] is not None
        ]
        return {
            "attempts": len(records),
            "successes": sum(1 for record in records if record["success"]),
            "healthy": all(record["success"] for record in records),
            "median_latency_ms": statistics.median(latencies) if latencies else None,
            "max_latency_ms": max(latencies) if latencies else None,
            "records": records,
        }

    def ping_ring(self) -> Dict[str, Any]:
        per_fabric = {
            route: self.ping_fabric(route) for route in sorted(self.fabrics)
        }
        records = [
            record
            for result in per_fabric.values()
            for record in result["records"]
        ]
        return {
            "attempts": len(records),
            "successes": sum(1 for record in records if record["success"]),
            "records": records,
            "per_fabric": per_fabric,
        }

    def stop(self) -> None:
        self.net.stop()


def _link_interfaces(link: Any, host: Any, switch: Any) -> Tuple[Any, Any]:
    if link.intf1.node is host and link.intf2.node is switch:
        return link.intf1, link.intf2
    if link.intf2.node is host and link.intf1.node is switch:
        return link.intf2, link.intf1
    raise ValueError("link does not connect the expected host and switch")


def build_topology(
    kind: str, base_profile: TcProfile = BASE_PROFILE
) -> TopologyDescriptor:
    if kind not in {"single", "dual"}:
        raise ValueError("topology kind must be single or dual")

    from mininet.link import Link
    from mininet.net import Mininet
    from mininet.node import OVSBridge

    net = Mininet(
        controller=None,
        switch=OVSBridge,
        link=Link,
        build=False,
        autoSetMacs=True,
    )
    switches = {
        "A": net.addSwitch(
            "sA", failMode="standalone", dpid="0000000000000001"
        )
    }
    if kind == "dual":
        switches["B"] = net.addSwitch(
            "sB", failMode="standalone", dpid="0000000000000002"
        )
    hosts = {rank: net.addHost(f"w{rank}", ip=None) for rank in range(WORLD_SIZE)}

    raw_links: Dict[str, Dict[int, Tuple[Any, Any]]] = {
        route: {} for route in switches
    }
    for route, switch in switches.items():
        for rank, host in hosts.items():
            link = net.addLink(host, switch)
            raw_links[route][rank] = _link_interfaces(link, host, switch)

    net.build()
    net.start()

    fabrics: Dict[str, Dict[int, WorkerFabric]] = {
        route: {} for route in switches
    }
    profile_records: List[Dict[str, Any]] = []
    for route in sorted(switches):
        subnet = 0 if route == "A" else 1
        addresses = {rank: f"10.{subnet}.0.{rank + 1}" for rank in hosts}
        for rank, host in hosts.items():
            host_intf, switch_intf = raw_links[route][rank]
            host.setIP(addresses[rank], prefixLen=24, intf=host_intf)
            host.cmd("ip", "link", "set", host_intf.name, "up")
            next_rank = (rank + 1) % WORLD_SIZE
            fabrics[route][rank] = WorkerFabric(
                name=route,
                local_ip=addresses[rank],
                next_ip=addresses[next_rank],
                port=FABRIC_PORTS[route],
                host_interface=host_intf.name,
                switch_interface=switch_intf.name,
            )
            profile_records.append(apply_profile(switch_intf.name, base_profile))

    return TopologyDescriptor(kind, net, hosts, fabrics, profile_records)


def smoke(kind: str) -> Dict[str, Any]:
    from mininet.clean import cleanup
    from mininet.log import setLogLevel

    setLogLevel("warning")
    cleanup()
    descriptor: Optional[TopologyDescriptor] = None
    try:
        descriptor = build_topology(kind)
        ping = descriptor.ping_ring()
        return {
            "kind": kind,
            "fabrics": sorted(descriptor.fabrics),
            "worker_count": len(descriptor.hosts),
            "fault_interface": descriptor.fault_interface(),
            "detector_interface": descriptor.detector_interface(),
            "profile_count": len(descriptor.profile_records),
            "all_profiles_netem": all(
                record["sample"]["kind"] == "netem"
                for record in descriptor.profile_records
            ),
            "all_profile_interfaces_up": all(
                record["operstate"] in {"up", "unknown"}
                for record in descriptor.profile_records
            ),
            "ping": ping,
        }
    finally:
        if descriptor is not None:
            descriptor.stop()
        cleanup()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("single", "dual"), required=True)
    args = parser.parse_args(argv)
    result = smoke(args.kind)
    print(json.dumps(result, indent=2, sort_keys=True))
    expected_attempts = WORLD_SIZE if args.kind == "single" else WORLD_SIZE * 2
    if result["ping"]["successes"] != expected_attempts:
        return 1
    if not result["all_profiles_netem"] or not result["all_profile_interfaces_up"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
