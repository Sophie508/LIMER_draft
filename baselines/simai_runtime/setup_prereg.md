# SimAI CPU setup and smoke-test registration — 2026-10-10

Change: build the unmodified SimAI compatibility candidate on the authorized
otakotak host in a dedicated CPU container. Expected: build succeeds, the native
AllReduce microbenchmark terminates, and output flow/completion data are nonempty
and internally consistent. This checks infrastructure only, not OptCC performance.

Pinned sources: SimAI f5efb5a93ea9be7db25a8843f9f7ff54044f6062 and ns-3
7e3cb5b88c99abcb582c5abc3919484a4805111b. Record the container image id/digest,
compiler, Python, CMake, source hashes and exact invocation. Do not update submodules
to their current heads. The candidate retains the old MockNcclGroup interface;
the original OptCC backend version is still unknown.

Build with Ubuntu 20.04's compiler/tooling, no Ninja, no GPU passthrough, no
privileged container, bounded CPU/memory. Keep build stderr, return codes and binary
hashes; existence of a symlink alone does not prove build success.

Smoke phase: run a documented native workload/topology first. Record all template
parameters (including GPUs/server and latency), then perform a separately registered
four-rank inter-server calibration before importing OptCC. No imposed detector or
cutover latency belongs in these native baseline runs. Keep every attempted run;
successful process exit alone is insufficient if there are no completed collectives.

If the original OptCC settings cannot be recovered, register subsequent runs as
independent reconstruction and do not label them as a reproduced paper figure.
