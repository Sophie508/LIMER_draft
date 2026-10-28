# Service detection and benefit-gated recovery protocol

This protocol evaluates the 2026-10-28 extension separately from the immutable
2026-10-27 reference results. All times are simulated times. The experiment does
not run CUDA or real GPUs and does not establish general grey-fault coverage.

## Questions and expected observations

The detection change introduces end-to-end service observations alongside the
legacy packet/gap observer. The canary-v4 detector retains the canary-v3
observable signals: repeated canary service-deadline violations, sender-observed
retransmission on distinct canaries, or an active original business transfer
with no real ACK progress for 40 ms. The first qualifying signal supplies the
path's alarm; the scorer does not choose whichever signal gives a favorable time.
The v4 extension additionally observes accepted data arrival spacing across all
QPs on each registered path. Only positive gaps whose adjacent payloads are both
976 bytes qualify. It freezes P10 from the initial 20 ms, then checks disjoint
10 ms windows with at least 64 gaps. Two consecutive P10 values above twice the
baseline plus 100 ns produce a service alarm. Insufficient windows reset the
confirmation; insufficient calibration is never retrained after the fact.
Each summary is independently reconstructed from raw receive and source/leg logs.

A canary uses the actual simulated transport and reports submission, completion,
or a retransmission. Calibration uses the first 20 ms only;
faults begin between 35 and 55 ms. The detector must not read injected fault
times, locations, loss rates, or end times. Injection truth is available only to
the post-run scorer. Severe service slowdown is eligible, including packets that
eventually arrive. This is an operational delivery-service alarm, not proof that
a particular physical component discarded a packet.

Expected observation: unlike the old gap observer, the new detector alarms for
sustained 25%-capacity service as well as blackholes and 0.5% packet loss. This is
a hypothesis until the registered held-out matrix completes.

The policy change compares the observable cost of waiting with the observable
cost of a three-leg relay. It must pay route measurement and coordination costs,
consider remaining unconfirmed work, and avoid reading future fault recovery.
Expected observation: a benefit gate retains completion under persistent faults
while avoiding unhelpful replacement for brief faults and expensive local relays.
Realized paired outcomes can falsify that hypothesis; they do not establish an
optimal online policy.

## Registration and development boundary

`tools/research_campaign.py` is independent of the historical campaign. Its
default development plan has 42 runs: seven conditions, two seeds, three policy
arms. Those cases support debugging and parameter selection, not final acceptance.
Development and validation seed ranges are disjoint. Freeze the algorithm and
parameters before registering validation. A failed validation remains a failed
validation; a subsequent change requires a new registration and new held-out
seeds, with the failed campaign retained.

The first formal campaign `validation-v1` used canary-service-v3 and failed the
quarter-capacity condition (42/60 timely trials, 18 missed directions). Its
registration, archives and scores remain unchanged. The v4 replacement must use
`--seed-base 102990000`, which is disjoint from every v1 seed, and a new campaign
directory. `--seed-base` is explicitly validated and frozen in the plan.

Default validation comprises 450 runs:

| Purpose | Conditions | Independent trials | Arms | Runs |
| --- | --- | ---: | --- | ---: |
| Primary detection | Persistent blackhole, 25% service capacity, 0.5% packet loss | 60 per condition | G11 benefit | 180 |
| Healthy controls | No injected fault | 60 | G11 benefit | 60 |
| Paired persistent recovery | The same three persistent conditions | First 20 of the same 60 trials | Add G10 no proxy and G11 always | 120 additional |
| Boundary recovery | 2 ms transient blackhole, 1 Gb/s local relay, no idle helper | 10 per condition | G10 no proxy, G11 always, G11 benefit | 90 |

`--include-delay` adds a fourth primary condition: the injected B access channel
has an 80 ms propagation delay, without loss or service-rate reduction. The fault
changes the actual ns-3 channel; it does not supply delay truth to the detector.
This adds 60 benefit trials and 40 additional paired baseline runs, for 550 runs.
The acceptance condition set is frozen in `plan.scoring.primary_conditions`; a
failure in delay cannot be hidden by passing the original three conditions.

`--include-slow-quarter` adds a policy boundary with B capacity at 25%, local
relay links at 1 Gb/s, and a dedicated long-phase workload of one round and 256
chunks per phase. Its approximately 8 GB of logical work is intended to leave time for the always
policy to activate a measured proxy; actual ACTIVATE events must establish this.
The slow-quarter boundary uses at least an 800 ms horizon in each arm, so
its longer workload can expose completion costs beyond the primary 400 ms cap. Unlike a blackhole, the direct B route still works
and can be faster than this proxy. This tests whether the benefit gate avoids
an actually available but costly replacement. It adds 30 validation runs.
Enabling both options gives **580 validation runs**, or 27 development runs with
`--development-trials 1`. The existing slow-proxy blackhole boundary remains;
it tests the distinct case in which some recovery is necessary for completion.

An optional 100 Gb/s local-relay condition adds 30 validation runs. Legacy
detection can be registered separately or with `--detector both`; comparisons
must name the detector and keep all its registered trials. Do not pool legacy
and service detection to raise a reported pass rate.

Every trial has a preregistered seed, fault node sampled uniformly from 16 GPUs,
and fault onset sampled uniformly over integer nanoseconds in [35, 55] ms.
The no-idle-helper condition retains the inherited fixed server-0 four-node fault
definition; its onset and transport stream vary, while its location does not.
Blackhole runs can be deterministic conditional on those inputs; counting 60
seeds does not imply 60 different stochastic packet-loss realizations.

### Loss-stream independence correction

The inherited injector writes `scene.seed + injected_node`, then the native
injector assigns stream `2 * (scene.seed + injected_node) + side`. The frozen
`validation-v2` schedule used consecutive scene seeds: its 60 benefit weak-loss
trials contain only 38 distinct derived stream pairs. Its empirical counts and
paired comparisons remain visible, but its nominal binomial confidence bound
must not be interpreted as independent-loss evidence.

Before inspecting that cohort's weak-loss outcomes, register a separate
`validation-loss-independent-v4` confirmation: 60 benefit-only weak-loss trials,
seed base 103100000 and stride 32. The reference native build, workload, detector
parameters and core auditors are unchanged. Each seed's node and onset are drawn
before execution; all 120 directional streams are distinct and disjoint from
the reference plan. Use this separate cohort for the final weak-loss detection
row, without pooling its counts with the original 60. The remaining three
detection rows and all recovery pairs remain from the main matrix. Thus the
final evidence comprises 580 main runs plus 60 prospective confirmation runs.

New plans made by the live generator default to stride 32 and record the actual
stream mapping. Historical plans must be reproduced with their own frozen
tooling, not regenerated with the changed live default.

Default workload is eight ring rounds, 16 chunks per phase. The default observation
horizon is 800 ms, including controls. The planned formal command below instead
freezes two rounds, 64 chunks per phase, and a 400 ms observation horizon; the
slow-quarter boundary retains its explicit one-round/256-chunk workload and
at least an 800 ms horizon. These
are new censoring horizons, not the old reference's 5 s cap. They can be changed
only before registration with `--horizon-ms`, `--rounds`, and `--chunks`.
All arms of a pair must share the exact topology, traffic, fault, seed, horizon,
and detector; only replacement policy and its availability may differ. Detection
monitoring continues until the registered horizon even if business work finishes.
Consequently a late alarm cannot vanish merely because the workload completed.

## Primary acceptance and secondary reports

A trial passes only if **every affected directed B path** alarms strictly less
than 100 ms after fault injection, with no pre-fault alarm and no unaffected-path
alarm anywhere in the registered observation window. The bilateral access-link
fault normally affects an outgoing and an incoming logical path. The no-helper
boundary affects eight paths. Correct-path first-incident latency is reported
separately and cannot substitute for the all-path criterion.

Each primary condition independently needs an empirical timely-success rate of
at least 95%. Late alarms, missing paths, mislocalizations, audit failures, runtime
errors and unrun registered cases stay in that condition's denominator. A run
with 100 ms exactly is late. No successful-only p95 is used for acceptance;
unobserved latencies remain unbounded when computing the all-trial p95.

For interpretation, report a separate 95% one-sided exact binomial lower bound.
For example, 60/60 gives a lower bound of about 95.13%; 57/60 gives an empirical
95% pass rate but does not give a 95% confidence lower bound of 95%. These bounds
apply per condition under the registered sampling assumptions, with no simultaneous
familywise correction across conditions. They do not broaden the tested topology,
traffic, fault severity, or deadline range.

Healthy controls report false-alarm trials and total verified monitoring exposure
separately. Failed or truncated monitoring is not a successful healthy control.

Recovery reports exact completion time for completed and independently audited
jobs. Unfinished jobs remain right-censored at the registered horizon and are
not assigned a fictional completion time. The capped completion score uses the
cap for unfinished/error/missing runs, with all counts disclosed. Pairwise
benefit-minus-always and benefit-minus-no-proxy capped differences are reported
along with the three completion flags; invalid pairs remain marked invalid.
An improvement in a capped score cannot by itself be called an exact speedup.

## Evidence and commands

The standalone tool writes an immutable registration, source/build/tool hashes,
one exact case file per attempt, compact results, and checksummed raw archives.
Large raw logs are pruned only after the existing archive tool has streamed and
verified their full contents. Interrupted and failed attempts are retained and
are not silently replaced on resume.

```bash
python3 tools/research_campaign.py plan --phase development --out /work/dev-plan.json
python3 tools/research_campaign.py register --phase development --build /work/build --out /work/dev
python3 tools/research_campaign.py execute /work/dev --workers 2
python3 tools/research_campaign.py summarize /work/dev

# Only after development changes and parameters are frozen:
python3 tools/research_campaign.py register --phase validation --build /work/build \
  --out /work/validation-v2 --include-delay --include-slow-quarter \
  --horizon-ms 400 --rounds 2 --chunks 64 --seed-base 103200000 --seed-stride 32
python3 tools/research_campaign.py execute /work/validation-v2 --workers 2
```

The example above creates a new separated-stream plan; it does not recreate the
historical v2 schedule. The actual supplemental confirmation is reproducible from
the exported v2 registration:

```bash
python3 tools/register_independent_loss.py --reference /work/results/validation-v2 \
  --build /work/build-v7 --out /work/results/validation-loss-independent-v4 \
  --seed-base 103100000 --seed-stride 32
python3 tools/research_campaign.py execute /work/results/validation-loss-independent-v4 --workers 8
```

New native evidence uses these minimum columns:

| File | Columns | Meaning |
| --- | --- | --- |
| `service_events.csv` | `timestamp_ns,event,path_id,token,bytes,last_progress_ns,spacing_ns,sample_count` | Canary `SUBMIT`, `COMPLETE`, sender `RETRANSMIT`, clock `ADVANCE`, original-transfer `STALL`, or receiver `SPACING` summary; extra columns are populated by their applicable event |
| `packet_events.csv` | Original packet columns plus `payload_bytes` | Source/leg and accepted RX payload sizes independently justify full-size spacing samples |
| `service_alarms.csv` | `timestamp_ns,path_id,signal` | Service detector decisions without fault truth |
| `policy_decisions.jsonl` | Native timestamp, source, decision, estimated costs | Observable stay/switch estimates and actual decisions |

`research_summary.json` gives per-condition denominators and bounded conclusions;
`research_trials.csv` preserves every registered attempt; `research_pairs.csv`
retains paired recovery comparisons. Validation success may be claimed only from
completed, verified primary groups, with healthy-control behavior and confidence
bounds disclosed alongside the empirical target.

Healthy runs in this simulator can be deterministic despite different unused fault seeds. Repeated healthy runs do not create new background-traffic coverage or justify a population false-alarm guarantee. Report this separately from the randomly placed/timed and loss-seeded fault trials.
