# Relay probe calibration against one accepted direct-recovery trace

Date: 2026-11-12. Read-only diagnosis; no source, registration, or raw result
changes, and no native simulation launched.

## Conclusion

In this retained direct-recovery run, a single full-chunk probe's
`chunk_bytes / max(leg_duration)` is substantially below the later aggregate
relay rate once several chunks overlap. The individual data-leg durations do
not disappear: in phase 2 their middle-leg medians remain close to the probe's
middle-leg duration. The difference is chiefly consistent with concurrency,
although the trace cannot identify concurrency as the only causal factor.

The same estimate is **not** a safe lower bound on early recovery throughput.
During the first two milliseconds after activation, startup, confirmation,
allocation, and incomplete pipeline occupancy sometimes produce less throughput
than the single-probe quotient. A future estimator must represent startup and
steady pipeline service separately and retain all control and helper costs.

This supports testing an explicitly paid multi-chunk probe train. It does not
justify multiplying the current rate by four, assuming free helper bandwidth,
or claiming that the candidate gate would have made a better decision.

## Evidence and reproducibility

Run: `pilot-v2/runs/sustained_25_early-direct-s111213001`, under
`otakotak:/home/suliu/data/LIMER_GRAY_GATE_2026-11-12/results`.

Only this accepted direct arm is used below. No candidate-arm traffic is mixed
into the calculation. The source/helper pairs are source 0 through helpers
(1, 5), and source 15 through helpers (12, 2), separately in phases 2 and 3.

- [Compact measurements](relay-probe-calibration.json).
- [Read-only extraction program](relay_probe_calibration.py).
- [Artifact checksums](relay-probe-calibration.sha256).
- Archive SHA-256:
  `f29f229cb40f15e2ba0a6da2b00a3c15ff999c993eff0dd1aa5647a122388278`.

The extraction rehashed the full 95,705,422-byte compressed archive, then checked
all consumed members (`peer_events.csv`, `leg_events.csv`,
`logical_events.csv`, `control_events.csv`, `phase_events.csv`) against the
frozen manifest. Their hashes are retained in the JSON. Large files were read
inside the archive rather than extracted or modified.

Descriptive windows were fixed as activation + [0,1), [1,2), [2,3), and [0,4) ms
before inspecting the numerical output. The program retains the first eight
relay routes for each pair, their three actual leg durations, physical-release
timestamps, logical completion timestamps, and whether they carry fresh chunks
or rescued suffixes.

Two measurements are kept distinct:

- **Data completion rate:** unique bytes whose last relay leg completed in the
  window, divided by the entire window duration. This follows the simulator's
  charged transport completion event; it is not merely injection or wire rate.
- **Logical ACK rate:** those relay bytes whose final paid logical confirmation
  completed in the window, divided by the same duration. It includes the delay
  visible to logical completion; early windows therefore differ substantially.

These are bounded subwindows, not whole-job normalized throughput or a claim
that a physical 10-Gb/s link exceeded its capacity.

## Initial paid probe and nearby real data

All probes carry 65,536 bytes over all three legs. Durations below are
microseconds; throughput values are Gb/s. The direct arm does not execute the
benefit estimator, so the quotient is a diagnostic application of the existing
formula, not a decision it actually logged.

| Phase/source | Probe leg 0 / 1 / 2 (us) | Single-probe quotient | Actual data middle-leg median for routes admitted in first 4 ms (us) | First 4 ms data completion | First 4 ms logical ACK |
| --- | --- | ---: | ---: | ---: | ---: |
| 2 / 0 | 0.304 / 229.511 / 0.304 | 2.284 | 238.231 | 4.832 | 2.735 |
| 2 / 15 | 0.304 / 253.664 / 0.304 | 2.067 | 239.954 | 4.813 | 2.715 |
| 3 / 0 | 0.304 / 190.665 / 0.304 | 2.750 | 236.946 | 5.562 | 3.465 |
| 3 / 15 | 0.304 / 318.735 / 0.304 | 1.645 | 241.252 | 4.639 | 2.410 |

In all four cases, the four-millisecond data completion rate is approximately
2.02–2.82 times the single-probe quotient. Even the final logical-ACK rate over
that window is about 1.20–1.47 times the quotient. These factors are descriptions
of this trace, not proposed tuning constants.

The four-millisecond fresh-chunk-only rates are 4.325, 4.325, 5.243 and
4.194 Gb/s respectively. Thus the comparison is not solely a burst of small
rescued suffixes being counted as full new chunks.

## Startup, concurrency, and helper work remain visible

| Phase/source | Data rate in 0–1 ms | 1–2 ms | 2–3 ms | Mean concurrent physical relay routes in 2–3 ms | Maximum |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2 / 0 | 2.551 | 0.524 | 7.864 | 3.931 | 4 |
| 2 / 15 | 2.473 | 0.524 | 7.864 | 3.961 | 4 |
| 3 / 0 | 1.802 | 2.621 | 9.437 | 4.000 | 4 |
| 3 / 15 | 2.301 | 0.524 | 6.816 | 3.738 | 4 |

All four first-millisecond logical-ACK rates are zero. The later rate cannot be
advertised as immediately available on activation. The event traces also show
that per-route physical release occurs at the last-leg completion, while logical
completion waits for its separately charged final confirmation.

The helper's own work does not vanish during this comparison. At probe launch,
each helper has about 30.83–30.93 MB of its own current-phase outgoing data left.
By activation it has about 19.36–19.83 MB left. At activation + 4 ms, it still has
roughly 11.12–14.25 MB left. The JSON preserves each helper's own remaining bytes
and own logical ACK rate at every window boundary.

For example, phase 2/source 0/helper 1's own ACK rate changes from 16.019 Gb/s in
the 1–2 ms window to 8.304 Gb/s in the 2–3 ms window as relay data completion
rises from 0.524 to 7.864 Gb/s. This is compatible with increased competition for
helper resources. It does not isolate how much is due to the relay versus the
helper's changing A/B allocation, so it must not be used as a precise marginal
interference cost without another controlled comparison.

## What this trace proves and does not prove

Supported observations:

1. Full-size relay data overlaps within the existing maximum of four physical
   route reservations and four helper buffers.
2. A per-chunk middle-leg duration is not the aggregate inter-completion period
   when several chunks are simultaneously served. In phase 2, similar per-chunk
   durations coexist with a much higher aggregate completion rate.
3. Startup and final confirmation remain material; a steady aggregate rate alone
   would overpromise in some immediately following windows.
4. The measured helper workload evolves and remains nonzero. Neither the route
   nor its interference is free.

Limits:

- Probe-to-activation time is 5.291–5.419 ms across these pairs (phase-2/source 0
  is 5.329961 ms). Approximately 11 MB of helper work completes between those
  points. The later data pipeline is therefore not measured at exactly the same
  state as the probe.
- The sample contains one accepted run, two phases and two pairs. The selected
  windows are descriptive, finite, and may contain allocation transitions.
- This direct arm lacks the candidate's additional paid helper-observation
  delays and different decisions. It cannot identify the candidate's
  counterfactual completion time or prove that replacing its rate estimate would
  reverse a decision.
- The observed data rate is offered-load dependent; source scheduling can leave
  physical capacity unused. It is neither an intrinsic path-capacity estimate
  nor an upper bound for all future traffic.
- A simple four-times multiplier could exceed real available capacity and erase
  helper contention. Keep the current source window of 32 and all physical caps.

## Proposed next minimal paid train probe (not implemented)

The purpose is to observe pipeline service under the currently available helper
resources, while separately measuring first-chunk latency and final-confirmation
cost. A prospective design could use a fixed **eight full 64-KiB chunks** per
candidate route: two physical-credit waves rather than one isolated chunk. Eight
is a proposed fixed geometry for review, not a value selected by a performance
sweep. Freeze it, its deadline, and its evidence schema before any experiment.

Execution and charging requirements:

1. The train follows the same delivered alarm and paid helper lending as current
   recovery. Existing traffic continues; there is no free pause or empty-network
   measurement phase.
2. Every probe chunk follows the actual three-leg route, with current topology,
   rates, buffers, retransmission behavior, and four-credit physical admission.
   Admit the next chunk only as real reservations permit.
3. Probe confirmations consume the **same total source logical-window budget of
   32**, together with business traffic, rather than allocating a second free
   window. Admission delays must be logged and charged. This is an explicit
   lifecycle extension relative to the present single probe.
4. Release physical probe reservation at the actual last-leg completion, like
   pipelined business data, while keeping its logical probe slot occupied until
   a paid final confirmation arrives. The current single probe holds its physical
   reservation until its health report; simply launching more such probes would
   measure a different, confirmation-limited pipeline.
5. Send a charged 96-byte per-chunk completion/health report if its declared
   fields fit the existing abstract control envelope. Each report carries
   route/train identity, phase/version, exact payload size, leg timing and
   completion timestamps. Report timing must come from delivered observations,
   not a controller's read of future or remote state.
6. Retain the existing paid helper reports. If before/after helper work counters
   are added to measure train interference, explicitly serialize and charge that
   added evidence; either fit a declared payload layout or increase message
   size. Do not obtain those counters from global state for free.
7. A fixed bounded train deadline cancels only owned probe routes, preserves
   charged bytes and late callbacks, and returns incomplete evidence on failure.
   It must not manufacture a successful bandwidth estimate from the fastest
   subset. Keep all failed or unfinished trains in the denominator.

At eight chunks, bare three-leg probe payload is **1.5 MiB** per candidate
(512 KiB across the network leg and 1 MiB over the two local legs), before packet
headers, retransmissions and control. Eight 96-byte per-chunk reports add 768
charged control bytes. The existing helper-query/report and distributed
coordination costs remain separate and still apply. These are explicit added
costs, not a free measurement.

Record at least request time, first admission, every route's admission and
last-leg completion, each paid final ACK, and train completion/failure. The
first-admission wait and the first-chunk latency are separate startup costs.
Report whole-train data completion and confirmation completion over wall time;
a tail inter-completion estimate may be secondary evidence, clearly labelled and
never substituted for the full train cost. Physical overlap, helper own work,
and unfinished probe count should accompany any claimed pipeline rate.

The expected diagnostic improvement is a service observation that can distinguish
slow individual chunks with useful overlap from an actually low aggregate
pipeline rate. Better gating or job completion remains an empirical question;
this document authorizes neither a source change nor a new campaign.
