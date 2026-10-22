# Mininet execution environment amendment — before fault campaigns

The newly authorized otakotak host is reachable. The original kernel-OVS
dual-plane topology passes connectivity on A and B. The unchanged healthy
workload completes all 6 collective/24 worker rounds, with both fabrics used,
one plan fingerprint per round, and no checksum/version/worker errors.

Change: execute the previously registered source repair and configurations in
fresh rootless-Docker containers on otakotak scratch. Expected: the repaired
receive owner survives the send-side abort; switch/stay verdicts and framed
transport correctness satisfy the original registered gates. This is a new
host environment, not a timing-equivalent rerun of archived VM measurements.

Runtime: Ubuntu 24.04/Python 3.12, kernel Open vSwitch; pinned task image
limer-mininet:2026-10-10-py312 (record its immutable id), four CPU equivalents,
4 GiB memory per lifecycle. Rootless containers require privileged mode to
permit Mininet's private namespace/sysfs mounts. This does not grant initial
host-root privileges. Existing host Docker/workloads/configuration are untouched.
The initial narrower-capability mounts failed; those preflight logs are retained.
Mininet reports an inability to raise some resource limits; preserve that warning
and measured sampling intervals rather than assuming precise real-time behavior.

Run original 10 switch and 10 stay repeats, and 3 each of hard/grayfast/transient.
At most two independent lifecycle containers concurrently, each with its own
network namespace, OVS database and result directory. A 1800-second wall guard
is an infrastructure failure, not a censored successful completion time. Preserve
every attempt and exit code. No new fix/retry silently replaces a failed repeat.
Report this concurrency/resource choice with timing results; reliability gates
remain completion/fingerprint/checksum based. Assess branch and retention gates
from source summaries, not process exit alone.
