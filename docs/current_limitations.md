# Current Limitations and Next Experiments

## What this snapshot supports

The current evidence supports three bounded statements:

1. Limiting one still-up access link from 100 to 20 Mbit/s reduces the matched
   four-rank AllReduce-like throughput to about 21%.
2. A detector isolated to the switch-facing peer counter can flag that
   persistent rate degradation in roughly 40-55 ms in this emulation.
3. A four-rank versioned route transition can move traffic to a pre-existing
   healthy fabric without observed CRC or mixed-version failures, although the
   fixed C3 performance gate currently passes only 1/3 repeats.

## Unsupported inferences

### It is not numerical AllReduce

Workers exchange repeated byte payloads and validate frame CRCs. They do not
perform reduce-scatter, summation, or all-gather semantics. `correctness.json`
proves framed transport, rank completeness, and route/version agreement, not
tensor equality.

### It is not a GPU, NCCL, or RDMA result

No GPU or training framework participates. There is no NCCL communicator,
PyTorch process group, RDMA queue pair, NIC firmware signal, checkpoint, or
optimizer state. The no-checkpoint property here means only that the synthetic
traffic loop changes route without restarting its round history.

### Detection is not switch-resident

The detector process polls Linux counters from outside the OVS bridge. It
models a management-plane switch-first interface. It does not demonstrate P4,
ASIC logic, a switch CPU agent, gNMI/SNMP integration, or a bounded switch
memory footprint.

### The end-host gate is not the proposed ML method

The v0 gate is a fixed explainable rule. It has no neuro-fuzzy fault classifier,
Gaussian-process uncertainty, confidence calibration, weak supervision, online
adaptation, or unseen-fault evaluation.

### Recovery assumes physical redundancy

C3 and C4 start with a healthy fabric B and persistent B-side TCP rings. This
tests coordinated reroute when a second path exists. It cannot recover a
strictly single-homed access link that has no alternative NIC, link, or route.

### The latency target is not met end to end

Counter-proxy detection is about 50 ms, but the host gate waits for one full
degraded round and takes about 5.27 s median in C3. The sub-millisecond
coordination stage does not make the complete loop millisecond-scale.

### Current formal faults are rate degradations only

All C0-C5 configurations use 0% random packet loss. Queue, drop, overlimit, and
error fields are collected, and the injector supports a loss percentage, but
the archived matrix does not validate gray packet-loss detection.

### Statistical scope is small

Three repeats per condition are appropriate for a first engineering sanity
check, not a publication-level claim about tail behavior, false-positive rate,
hardware diversity, or production workloads.

### One result field has an ambiguous name

For C3, top-level `fault_period_retention` summarizes every post-injection round,
including recovered B rounds. Use nested `fault_window.fault_period_retention`
for the isolated degraded A round and `post_recovery_retention` for the recovery
gate. See [`experiment_design.md`](experiment_design.md).

## Prioritized next experiments

### 1. Isolate the C3 standby-path effect

Keep the existing `>= 0.9` gate and all other parameters fixed. Compare:

- idle B ring, matching the current implementation;
- low-rate B keepalive before the fault;
- explicit pre-fault performance rounds on B.

The hypothesis is that an idle or cold B-side TCP path causes the first two
recovery rounds to lag. This is not yet proven; the controlled comparison must
either support or reject it.

### 2. Reduce host-confirmation latency

Emit step-level duration and progress evidence while a collective round is in
flight. Compare time-to-confirm against the whole-round gate while retaining a
transient condition like C5 to measure false-trigger suppression.

### 3. Add an orthogonal gray-loss matrix

Predeclare low non-zero loss levels with the rate held constant, distinguish
configured loss from congestion drops, and test whether the same switch-facing
signals retain high recall without directly observing the injector state.

### 4. Replace proxies one boundary at a time

First connect the counter interface to realistic streaming telemetry and measure
poll/stream overhead. Next train and calibrate the end-host classifier and GP on
separate traces. Only then move the workload to PyTorch/Gloo for CPU numerical
AllReduce and to `nccl-tests` on a GPU host.

### 5. Implement real collective recovery

The final systems step is a safe-point protocol that rebuilds or changes the
actual collective communicator consistently across ranks without checkpoint
rollback. It needs failure-timeout handling, partial-READY behavior, rollback
or abort semantics, and real GPU validation; the current TCP route-version
protocol is only its executable scaffold.
