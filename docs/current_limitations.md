# Current Limitations and Next Experiments

## Evidence boundary

Two generations must not be mixed:

- `results/` is immutable legacy CPU v0 evidence. Its closed loop uses a
  coordinated whole-ring A-to-B transition and remains a valid record of the
  original minimum demo.
- `results_active_active/` contains the measured active-active v1 matrix. Its
  21 formal runs prove both-fabric healthy use and policy-specific plan
  correctness in this emulator; the website displays only the three complete
  `AA3_LOCAL` repeats.

All 21 v1 runs completed with correctness `pass`; 20/21 predeclared performance
gates passed. The retained failure is `aa3_global_rep02`, an explicit global
comparison whose post-recovery retention was 0.882. These are emulator results,
not evidence of production performance, hardware compatibility, or large-scale
training behavior.

## What the prototype can establish

The complete Linux/Mininet artifacts let the CPU prototype answer five bounded
questions:

1. Do Fabric A and Fabric B both carry non-zero normal traffic under the
   balanced active-active schedule?
2. Does a 100-to-20 Mbit/s impairment on worker 2's A egress remain `UP` while
   reducing completed collective-like throughput?
3. Can a distinct switch-facing counter raise a suspicion without reading the
   injector qdisc?
4. Can every rank commit the same route-plan version and fingerprint at one
   completed-round boundary?
5. Does localized recovery change exactly worker 2's three baseline-A send
   slots while leaving workers 0, 1, and 3 unchanged?

Retention is always divided by the matched active-active baseline from the
same run. Failed repeats remain part of the denominator.

## Unsupported inferences

### It is not numerical AllReduce

Workers exchange framed byte payloads and validate CRC, round, step, version,
and route-plan agreement. They do not perform reduce-scatter, summation, or
all-gather. Transport correctness is not tensor equality.

### It is not a GPU, NCCL, RDMA, or training result

No GPU, training framework, NCCL communicator, RDMA queue pair, checkpoint, or
optimizer state participates. “No rollback” means only that the synthetic
round sequence continues across a route-plan commit.

### Detection is switch-facing, not switch-resident

The Python sampler polls the Linux counter on the OVS-facing endpoint from the
root namespace. It models a switch-first management interface but does not
demonstrate ASIC or P4 logic, a switch CPU agent, gNMI/SNMP streaming, or a
bounded switch memory and compute budget.

### The end-host gate is not the proposed ML method

The current rule combines switch suspicion, completed-round slowdown, and
alternate-path health. It has no neuro-fuzzy fault classifier, Gaussian-process
uncertainty, calibration study, weak supervision, online adaptation, or
unseen-fault evaluation.

### The fault is directed, not a full physical-link model

Active-active v1 rate-limits only `w2 -> Fabric A` egress. This is enough to test
the corrected locality semantics, but it does not model a bidirectional cable
fault or independent ingress impairment. The public diagram labels the arrow
direction explicitly.

### Recovery still assumes a usable alternate path

Fabric B already carries ordinary traffic before the fault; it is not a cold
backup. Localized rerouting therefore assumes worker 2 has a healthy alternate
connection. A strictly single-homed access link cannot be repaired by route
selection alone.

### All-rank coordination is a consistency scaffold

All ranks receive the plan because each receiver must listen on its
predecessor's selected fabric. This proves coordinated plan installation, not a
real PyTorch process-group or NCCL communicator rebuild. Timeout, partial-READY,
process death, and control-channel partition handling remain incomplete.

### End-to-end millisecond recovery is not established

The switch sampler targets a 20 ms interval, but the host gate waits for an
entire degraded round before confirmation. Latency artifacts report switch,
host, coordination, commit-to-completion, and fault-to-restoration stages in
milliseconds. The formal numeric target is unspecified, and raw stage values
must not be converted into a claim that millisecond end-to-end recovery was
achieved.

In the three formal `AA3_LOCAL` repeats, median switch-suspicion latency was
about 2.78 s and median fault-to-completed-recovered-round latency about 3.96 s.
Coordination itself was sub-millisecond, but it begins only after the slow
round and host gate. The measured bottleneck is therefore confirmation timing,
not plan dissemination.

### Fault and statistical coverage remain narrow

The current v1 matrix uses a 20 Mbit/s directed rate cap and 0% configured
random loss, plus one 100 ms transient. Three repeats per scenario are an
engineering sanity check, not a publication-level tail, recall, false-positive,
or hardware-diversity result.

## Prioritized next experiments

### 1. Replace whole-round confirmation with step-level evidence

Emit duration and progress while a round is in flight. Compare time-to-confirm
against the current completed-round gate while retaining the transient scenario
to measure false-trigger suppression. The change is successful only if latency
falls without turning the 100 ms transient into a recovery commit.

### 2. Expand concrete fault profiles

Predeclare separate experiments for:

- bidirectional 100-to-20 Mbit/s degradation;
- constant-rate low non-zero packet loss;
- queue buildup and congestion drops; and
- several fault durations around the confirmation boundary.

Configured impairment, observed counters, and congestion-induced drops must be
kept as separate fields. This replaces ambiguous shorthand with explicit
variables and expected observations.

### 3. Replace telemetry proxies one boundary at a time

First connect the existing Layer 1 interface to a realistic streaming source
and measure sampling delay, memory, and CPU cost. Then evaluate the end-host
classifier and calibrated uncertainty estimator on separately generated train,
calibration, and test traces. Do not infer switch feasibility from Python
process overhead.

### 4. Add realistic collective simulation up to 128 GPUs

Use SimAI as a separate model-backed experiment track for small-to-medium scale
collectives, with at most 128 simulated GPUs initially. Calibrate its topology,
collective schedule, and fault assumptions against the measured CPU emulator
where the two overlap. SimAI output is not interchangeable with Mininet packet
and counter evidence.

### 5. Implement real collective recovery

Validate numerical CPU collectives before moving to GPU `nccl-tests`. The final
systems step must adapt or rebuild the real communicator at a safe point,
handle partial coordination and timeouts, and continue without checkpoint
rollback. The current route-plan protocol is only the executable scaffold for
that work.
