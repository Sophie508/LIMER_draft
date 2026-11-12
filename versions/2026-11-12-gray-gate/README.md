# Gray-fault switching-benefit revision — 2026-11-12

Status: all 20 pilot and 30 confirmation attempts are retained. There are **49
valid records: 47 completed and two unfinished**, plus **one invalid** terminal
helper-release attempt. Source/build identities, 1,505 compact files, 49 raw
archive receipts and regenerated summaries have been checked. See
[complete results](RESULTS.md), [per-attempt rows](trials.csv) and
[verification](verification/compact-v2.json).

The separate `project-terminal-fix` repairs the newly found terminal cleanup
defect without changing the gate formula or auditor. It passes 216 local tests;
all ten selected native regressions passed execution and observation audits.
The original `project` and its failed confirmation record stay frozen. See the
[repair results](TERMINAL_REPAIR_RESULTS.md),
[repair protocol](research/TERMINAL_REPAIR_PROTOCOL.md) and
[repair diff](review/terminal-fix.diff).

All ten repair runs retain the original job-completion timestamps, policy/alarm
streams and precompletion control records; final-phase helper leases now close
through paid releases. The other 20 repair registrations are intentionally
unrun. This targeted repair is not full performance qualification.

The initial native candidate was stopped after one valid control and one invalid
candidate attempt. Its auditor conflated a phase admission reset with physical
resource release. [The failure record](research/FAILED_ATTEMPTS.md), frozen
`project-v1`, and [compact original evidence](evidence-v1/COMPACT_MANIFEST.json)
remain intact. The current `project` corrects that audit and is registered as v2;
the native binary, policy, conditions and seeds are unchanged.

The later v2 failure is different: a real paid release arrives after the final
business ACK advances the global phase, so the old callback skips cleanup.
See [both retained failures](research/FAILED_ATTEMPTS.md). Finishing business
data does not excuse a failed lifecycle audit.

The immutable baseline is commit
[191f4349](https://github.com/Sophie508/LIMER_draft/tree/191f4349da2eb7ed3e7990835792c18d8ade7ec0/versions/2026-11-12-throughput).
Its 73.88–78.07% healthy-normalized throughput result uses direct recovery, not
the previous benefit gate. The previous weak-loss gate regression is retained.
That earlier workload has 30 phases / 15 GiB; this diagnostic uses four phases /
2 GiB. Its normalized ratios cannot be pooled with or directly compared to the
earlier workload's 70%–80% target.

## What the completed campaign supports

| Confirmation condition | Direct recovery | Candidate gate | Interpretation |
| --- | ---: | ---: | --- |
| Transient slowdown to 25% for 20 ms | 80.313 ms | 72.675 ms | Avoiding replacement is faster here |
| Sustained 25%, helper-local links at 1 Gb/s | 109.149 ms | 95.444 ms | Avoiding a slow alternative is faster here |
| Sustained 25%, ordinary helper-local links | 82.404 ms | 95.444 ms | Candidate is too conservative; direct recovery wins |
| Weak loss, confirmation seed | 88.572 ms | 91.503 ms | Candidate remains slower on this draw |

These are paired finite measurements, not an overall superiority claim. The
candidate also has a retained invalid 50%-capacity case; with no healthy helper,
both arms remain unfinished at the observation deadline. The small diagnostic
matrix does not establish a population-level 95%-within-100-ms guarantee.

**Detection still has a concrete failure:** in the 50%-capacity condition, all
four repaired arms detect path 13 after 8.726741 ms but never alarm on affected
path 721 before the 250-ms monitoring horizon. The trial therefore remains a
miss under the all-affected-paths criterion. This occurs with both the original
and repaired detector streams; fixing lease cleanup does not fix detection.

## Research question

When a link continues delivering at reduced speed, can the controller choose
whether to open a GPU relay so that the remaining communication finishes sooner,
after accounting for probe/coordination, stalled tails and the helper's own work?

This is a simulation-only policy study. The candidate is not a complete NCCL,
R2CC, tensor AllReduce or physical GPU implementation. R2CC is relevant prior
work with live migration, proxy forwarding and model-based schedule selection;
its performance numbers must not be directly compared to this simulator's.

## Candidate and controls

- `G10`, `always`: adaptive allocation, no recovery; detector runs in shadow.
- `G11`, `always`: direct recovery after alarm and route validation.
- `G11`, `benefit`: preserved previous heuristic.
- `G11`, `benefit_v2`: explicit new candidate forecast and temporary-loan lifecycle.

The detector is frozen. Native inputs never expose injection truth to the gate.
The candidate uses source-observed progress, a paid three-leg route probe, and
paid helper-work reports. Rejected temporary helper loans are released using
charged messages guarded by phase and lease identity. Forecasts are heuristics,
not oracle predictions or guarantees about future fault duration.

Physical capacities, source window, control delays and final ACK accounting are
unchanged from the pipelined shared-helper release. The helper mode remains an
explicit extension of the collaborator's original idle-only architecture.

## What the gate actually estimates

Imagine a sender with most data already delivered but a small B-path tail still
unacknowledged. The old gate can divide those few bytes by a recent average rate
and predict an almost immediate finish, even though the tail has made no progress
for milliseconds. V2 records the oldest unfinished B chunk's no-progress age.
After the existing 2-ms observation cadence it uses that age as a persistence
forecast. It is not a guarantee that the tail will remain stuck.

For the alternative path, a complete paid probe measures all three relay legs.
The estimator distinguishes four physical transfer credits from the source's
32 outstanding-confirmation slots. It always charges the complete first-chunk
and final-ACK latency. This corrects the old credit model without increasing any
physical limit.

Both helpers receive a paid query and return their own remaining outgoing work
and recent acknowledged service. The gate compares the maximum predicted finish
time of the affected source and the two helpers, including a simple equal-byte
forwarding opportunity cost. Missing or stale reports cannot authorize a switch.
This is a local current-phase heuristic: it does not predict every rank's
critical path, the RX helper's incoming contention separately, or future fault
recovery. Actual contention still affects the simulator's measured job time.

The gate controls the first activation in each phase. It does not continuously
optimize among alternative helper pairs. Rejected or unsuccessful initial
temporary loans are released through paid messages. A 20-ms bound cancels only
the corresponding health probe, retaining its wire cost and failed outcome.
An already configured binding keeps its helper pair while refreshing health;
source completion and phase reset end its use. An explicit lease release waits
for physical reservations to drain. Phase reset ends admission eligibility while
old physical reservations remain independently accounted until their real release.

See the [registered experiment protocol](research/EXPERIMENT_PROTOCOL.md) and
[R2CC scope comparison](research/R2CC_SCOPE.md). The experiment contrasts the
complete estimator and lifecycle revision with earlier arms; it is not an
isolated estimator-only ablation.

## Evidence workflow

Read [the implementation plan](../../docs/superpowers/plans/2026-11-12-gray-gate.md).
Source owners are separated into policy/replay, resources/audit, and registered
experiments. Root integrates and launches all remote runs on otakotak, one at a
time initially. Every invalid, unfinished and negative attempt is retained.

Pure rate faults have zero injected loss. `quarter` always means 25% remaining
capacity; `slowdown` adds an explicit `slowdown_fraction` field. Primary fault
onsets occur after the 20-ms calibration interval, and the detector never gets
the configured fault time, duration or fraction. Healthy and hard-fault controls
remain part of the comparison. Pilot cases are development, not independent
proof of a 95%-within-100-ms population target.

`project/third_party` reuses the identical vendored dependency via a relative
symlink. Clone the complete repository to resolve it. Build and source hashes
must freeze before executing any registered case.

Use [REPRODUCE.md](REPRODUCE.md) for inspection and fresh-run commands,
[review/README.md](review/README.md) for the diff scope, and
[NOVELTY_AUDIT.md](research/NOVELTY_AUDIT.md) for prior-work boundaries.
