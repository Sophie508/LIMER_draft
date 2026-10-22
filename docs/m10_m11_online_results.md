# M10/M11 online slowdown detection and route-cost results

## Objective and implementation branch

Sophie confirmed that severe slowdown is also eligible for detection. We first
implemented runtime pending-flow ownership (M9), then inspected the pinned
RDMA stack for causal within-transfer progress. Sender `snd_una` advances on
ACKs; completed QPs disappear. The observer therefore sums completed flow bytes
and active acknowledged bytes. This is ACK progress, not permanent-loss proof
or instantaneous receiver delivery. Fault metadata never enters the decision
interfaces. All results here are simulation on CPU; no physical devices.

The unchanged candidate freezes the median of the first four positive, fully
busy per-path service samples. Three subsequent fully busy samples below half
that reference emit one alarm. Idle windows interrupt evidence. It can miss
uncalibrated/idle paths, weak loss and brief events. This development heuristic
has not received broad held-out validation and does not resolve the full <100-ms
constraint. M7/M8 loss-only results and failures remain unchanged.

## M10 causal detection development

Four ranks execute three consecutive 3-MiB network-only rings, 72 transfers and
136 endpoint dependencies, at 1-Gb/s access rates and 500-ns propagation. All
eight sender/plane paths report every 2 ms: 64 bytes per report on a separate,
reliable 10-Mb/s FIFO with 1-ms propagation. Reports incur modeled service cost,
not data-fabric contention. Shared clocks, reliable counters and management are
explicit assumptions. There is no route actuation in M10.

| Frozen v2 development case | Observed outcome |
|---|---|
| Healthy | No alarms |
| Persistent rank-2 A 1→0.2-Gb/s service at 50 ms | Localized alarm after 9.1536 ms; no other/pre-event alarms |
| Same service reduction for 2 ms, with full rate/pacing restoration | No alarms |
| Persistent reduction, 120-ms report propagation | Localized alarm after 128.1536 ms; deadline fails |

The first v1 ledger is retained. Its registered brief control alarmed after
9.1536 ms because a QP created during the reduction retained its 0.2-Gb/s pacing
cap after device restoration: that transfer took 31.562664 ms. The scene did
not restore delivery promptly. The v2 injector explicitly changes configured
directed NIC serialization and active DCQCN current/maximum/target rate caps at
both reduction and restoration. Detector thresholds and logic are unchanged.
This is a changed fault model, not an algorithm-only improvement or retroactive
reclassification of the v1 control. It is not a hidden physical-link fault model.

All four v2 engineering lifecycles drain. Independent auditing reproduces all
actual online alarms, 2920 delivered reports and 226492416 acknowledged bytes.
It verifies report serialization/arrival, busy evidence against QP lifetimes,
monotonic credit and final per-path volume. Source, binary, inputs and 39 shared
libraries match the prospective registration. Development is deterministic;
these four cases do not establish population recall or false-alarm confidence.

## M11 finite-horizon closed loop

The M11 target connects the same online alarm to an observable sender-service
heuristic and the validated pending-flow transaction. Delivered reports carry
pending and launched unacknowledged bytes for both planes, increasing cost to
96 bytes per report. The channel remains 10 Mb/s with 1-ms propagation and 2-ms
sampling. Steady offered report traffic is 3.072 Mb/s (30.72% of service).

The heuristic compares parallel serialized-work proxies:
`stay=max((I_A+W_A)/r_A,(I_B+W_B)/r_B)` and
`switch=max(I_A/r_A,(I_B+W_B+W_A)/r_B)+10 us`.
Only pending A work can move. B service is the minimum of its calibrated and
last positive fully busy observed rate, at most 20 ms old at decision arrival;
unknown/stale/zero service selects stay. The 10-us cost budget exceeds the
measured 8.145-us four-rank transaction in this declared model. This heuristic
does not solve the collective critical path or predict future congestion.

Eight cases are registered before launch: four route arms in two alternative
conditions. All use fourteen consecutive 3-MiB rings, 336 transfers and the same
prescribed root-release schedule (0,100,...,1300 ms), with endpoint dependencies
between rounds. At 312 ms, rank-2 A configured egress service falls from 1 to
0.2 Gb/s. Rank-2 B initially serves at either 1 or 0.1 Gb/s; all other accesses
are 1 Gb/s. The release schedule is workload input, not detection knowledge of
injection. No random loss or compute/reduction model is included.

All arms use the same channel and per-report cost; total report bytes depend
on the measured lifecycle duration. Stay submits no route change;
fixed requests localized switching at workload start; oracle requests it at
injection; candidate has no scripted request and uses delivered observations.
Fixed and oracle changes still pay coordination and preserve launched ownership.
The oracle arm supplies timing/identity, not optimal route selection.

| Alternative B (Gb/s) | Stay (ms) | Fixed switch (ms) | Oracle-timed switch (ms) | Observable candidate (ms) | Candidate action / alarm delay |
|---:|---:|---:|---:|---:|---|
| 1.0 | 1545.674 | 1339.485 | 1339.485 | 1339.485 | Switch / 9.2304 ms |
| 0.1 | 3958.544 | 5360.714 | 5190.811 | 3958.544 | Stay / 35.2304 ms |

Times are total network-DAG completion from workload start, including delay
before detection and prescribed releases, rather than post-switch throughput.
The candidate improves completion by about 13.34% over stay in the faster-B
scene and matches stay in the slower-B scene. Fixed switching makes the latter
about 35.42% slower. These are bounded deterministic measurements, not confidence
intervals, optimality, real training gains or an OptCC performance comparison.
Fixed/oracle arms may avoid exposing the affected path; their absence of alarms
is not scored as a candidate detection miss or success.

The fast-B candidate changes 31 still-pending transfers after its request;
fixed and oracle change 41 and 32. Slow-B candidate commits nothing, while fixed
and oracle change 41 and 38. Each activated plan uses 768 modeled control bytes.
The candidate's observed alarm leads directly to its audited cost decision and
request; fault time/identity are used by the scorer and oracle only. Both
candidate conditions have zero pre-event/unaffected-path alarms in these runs.

All eight workloads drain and pass independent FIFO, ACK, queue-byte, detector,
policy-arithmetic, release-time, endpoint-dependency and immutable ownership
checks. Final replay audits 96224 delivered reports and 2113929216 acknowledged
bytes; input/source/binary and all 39 shared-library hashes match registration.
The full Linux suite passes 279 tests; macOS passes with its three existing skips.

## Artifacts, limits and continuation

Remote ledgers are `runs/m10_progress_v1/`, `runs/m10_progress_v2/` and
`runs/m11_closed_loop_v1/` under
`/home/suliu/scratch/LIMER_WORK_2026-10-10`. Raw data remains on otakotak; local
thin summaries are in `/Users/sophie/Documents/LIMER_WORK_2026-10-10/`.
Final audit records are `logs/m10_final_audit_v2.json` and
`logs/m11_final_audit_v1.json`. No experiment or model amendment was discarded.

This loop implements the simulation pipeline under a declared configured-rate
scene. It does not establish weak-loss detection, physical-hop localization,
uncalibrated/idle path coverage, cancellation/replay of launched stalls,
unreliable management, multi-invocation isolation or numerical AllReduce.
Next validation must freeze this candidate against fresh impairment/control
conditions, changing B service, bursty/sparse demand and report loss/delay, then
cross route policy with the ring/OptCC schedules. Keep <100 ms as an unresolved
constraint until the registered envelope passes; the two timely cases are not
a general guarantee.
