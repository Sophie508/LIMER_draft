# M13 business-delivery detection results

## Latest independently validated outcome

The implemented causal traffic-compensating version has **400/400** correctly localized fault decisions strictly below 100 ms in fresh 460-case validation. Per-condition empirical 95% verdict: **PASS**. Sixty primary controls and a separately registered 60-case high-traffic control supplement have zero alarms. All lifecycles pass independent final audit; development and controls are not added to fault acceptance denominators. This is a bounded one-hop simulation repair under a 10 Gb/s, representative-probe and configured-collector envelope, not universal gray-fault coverage or joint collective recovery. The original fixed-budget failures remain below.

## Initial small-probe candidate and measured failure

The class-separated Python/native candidate is implemented. Corrected development completes all 149 prospective registrations with engineering PASS, exact report/packet replay and zero false alarms in 65 controls. It does **not** meet the per-condition empirical 95% below 100 ms requirement: 73/84 fault registrations are timely. No held-out small-probe acceptance campaign is launched after this failure.

| Registered condition | Timely <100 ms | Late | Miss | P95 ms | False alarms |
|---|---:|---:|---:|---:|---:|
| low_selective | 16/20 | 4 | 0 | 121.626 | 0 |
| low_businessloss | 13/20 | 6 | 1 | 175.687 | 0 |
| low_loss | 20/20 | 0 | 0 | 64.223 | 0 |
| high_loss | 3/3 | 0 | 0 | 52.394 | 0 |
| low_sparse | 3/3 | 0 | 0 | 57.000 | 0 |
| low_idle | 3/3 | 0 | 0 | 60.979 | 0 |
| low_processing80 | 5/5 | 0 | 0 | 54.983 | 0 |
| low_reorder80 | 5/5 | 0 | 0 | 54.288 | 0 |
| low_overload | 5/5 | 0 | 0 | 33.458 | 0 |

Six low-profile controls (nominal, pause, mild congestion, dense 40 ms reordering, sparse 40 ms reordering, application 40 ms deferral) each have 10 lifecycles. High-profile pause adds five. All have zero candidate alarms. These finite checks do not establish a population false-alarm bound. Sparse/idle/high regression groups have only three lifecycles, and severe-delay groups five; they are development checks, not adequate held-out acceptance evidence.

## What changed and why

M12 can miss business harm while its small probes remain healthy. M13 exports distinct business/probe acceptance and delivery counts plus receiver-observed sequence gaps. Each class has independent source sequence numbers. A gap starts only when a higher sequence arrives and is erased when its missing packet arrives. A gap aged at least 40 ms can alarm. Separately, two adjacent aligned business-only service windows with at least 32 accepted packets and at most 60% delivery alarm without being masked by healthy probes. The frozen M12 rule remains an independently scored shadow baseline and candidate fallback. Each path emits only its first alarm. Injection timing, location, errors and private drop counters are scorer-only.

The paired algorithm comparison uses **the same M13 delivered reports and 96-byte collection cost**, not older M12 seeds: selective timely decisions improve from 7/20 to 16/20; application-loss decisions from 4/20 to 13/20. Both remain below target. Every selective lifecycle realizes business loss; 19/20 application-loss lifecycles do. The one zero-realized-loss registration remains a miss in the denominator and is not described as failed detection of actual damage.

## Guard sensitivity: speed versus false alarms

This is retrospective first-alarm-time analysis on development reports, not new native or held-out validation. Counter lanes are unchanged; lowering a gap guard can only introduce an earlier gap alarm, so first decision times are the minimum of original alarms and newly qualified causal RX reports. Replaying the original 40 ms guard reproduces every registered score.

| Gap guard | Selective timely /20 | Application loss timely /20 | Sparse 40 ms false-alarm runs /10 | Application 40 ms false-alarm runs /10 |
|---|---:|---:|---:|---:|
| 0 ms | 19 | 18 | 10 | 10 |
| 10 ms | 19 | 17 | 10 | 10 |
| 20 ms | 18 | 16 | 10 | 10 |
| 30 ms | 18 | 15 | 10 | 10 |
| 40 ms | 16 | 13 | 0 | 0 |

Dense 40 ms wire reordering also false-alarms in all 10 controls for every tested guard below 40 ms. Even the zero-wait gap rule supplies only 18/20 timely application-loss decisions in these records. This is a bound on this retrospective gap/counter family and this finite ledger, not an impossibility theorem for every new observation architecture. Alarm semantics and injection-to-decision timing are unchanged.

## Observation costs and assumptions

Reports contain 13 observable fields: path, batch, side, total/data/probe counts, sample/arrival times, lane guard, data/probe gap counts and oldest gap ages. A 68-byte serialized payload plus modeled 20-byte IPv4 and 8-byte UDP overhead costs 96 bytes per report copy. The abstract collector adds no link-layer header; it is not a second packet topology. Three copies of 1600 samples cost 460.8 KB/lifecycle and 7.3728 Mb/s steady load (73.728% of 10 Mb/s service). Every offered copy is charged even if lost. Same-path small probes still cost nominally 17.92 Mb/s/path. Data and probes together offer 97.92% of each low 100 Mb/s link; the 10%-capacity background control is therefore mild overload, not below-capacity traffic.

The model has eight independent one-hop UDP paths, fixed 2/A fault location, aligned clocks, finite 250 ms source traffic and a 600 ms observation drain. Low/high business rates are 80 Mb/s and 1 Gb/s. Application loss is applied after UDP receipt before application delivery; small probes bypass that stage. It is distinct from >128-byte selective network loss. Neither stage establishes real hardware fault coverage. No tensor reduction, RDMA collective, route actuation or recovery benefit is measured here.

## Preserved setup failure and provenance

The initial v1 development injector mistakenly gave sparse_reorder40 an 80 ms delay. It is interrupted with all 149 registrations retained: 19 verified process lifecycles, five interrupted/unverified attempts and 125 unrun attempts. It supplies no target acceptance evidence. Corrected v2 records actual injection parameters and rejects any mismatch with the registration; IDs 62000–62148 are fresh. Corrected smoke IDs 59100–59102 include a late selective case and are only engineering checks. Original smoke IDs 59000–59002 are separately retained.

Corrected development independent audit verifies all 715200 delivered report rows, 10388280 probe packets, encoded payloads, FIFO service, actual source/application packet events and exact native/Python candidate plus shadow-baseline decisions. Source/binary/library/image hashes are frozen. M12 sources, 740-case validation and failed boundary ledgers are preserved.

Primary server artifacts: `/home/suliu/scratch/LIMER_WORK_2026-10-10/runs/m13_development_v2`, `logs/m13_development_v2_final_audit.json`, `logs/m13_guard_sensitivity_v2.json`, `m13_source_frozen_dev_v2`. Local thin artifacts and review package live under `/Users/sophie/Documents/LIMER_WORK_2026-10-10`.

## Research basis

[RFC 7799](https://www.rfc-editor.org/rfc/rfc7799.html) distinguishes generated measurement traffic from observations of existing traffic and requires considering measurement load. The observation cost is therefore part of the intervention, not free instrumentation. [SprayCheck](https://arxiv.org/html/2605.03702v1) uses adaptive-routing packet distributions and discusses access-link count/NACK extensions; M13 is not a SprayCheck reproduction and does not claim novel invention of receiver sequence-gap or access-counter observation.

## Cost-preserving workload-shaped probe experiment

A separately frozen 150-registration development experiment implements representative 1500-byte probes, using the actual business packet size rather than a value chosen just above the artificial 128-byte fault cutoff. They traverse the same modeled application handler as data. The nominal byte budget remains 17.92 Mb/s/path: the rate drops from 35000 to 1493.333333333 packets/s. Class sequences and processing RNG streams remain separate. Both arms use fresh, unpaired IDs 66000–66149; this is an observation intervention, not a matched-draw algorithm-only comparison.

| Condition | Small probe timely | Business-shaped probe timely |
|---|---:|---:|
| selective | 17/20 | 20/20 |
| businessloss | 14/20 | 18/20 |
| idle | 5/5 | 2/5 |

All 60 control registrations have zero alarms. The full-coverage empirical gate remains FAIL: shape matching improves the active selective condition in this finite sample, but application loss remains below 95% and reduced probe opportunity hurts idle recall. No held-out success claim follows from the 20/20 selective development result.

All 150 process lifecycles and their independent final audit pass: 720000 delivered reports, 5452200 probe packets, exact source/application event reconstruction and native/Python decisions. Wire-class audit parses the actual PPP/IPv4/UDP/batch headers; it does not infer traffic class from packet size. Probe payload length and modeled injection parameters are verified against each trial registration.

Nominal byte budgets match. The discrete source schedule yields 8715 small packets or 372 representative packets per path/lifecycle: 557760 versus 558000 actual probe bytes. This 240-byte packet-boundary difference is charged explicitly, not hidden as exact equal realized bytes. The independent files are `runs/m13_representative_v1`, `logs/m13_representative_v1_final_audit.json`, and `m13_source_frozen_probe_v1` on otakotak.

## Constant representative probes in an explicit 10 Gb/s envelope

The constant-frequency observation intervention passes independently seeded validation: **400/400** registered faults are correctly localized strictly below 100 ms, each declared condition meets the empirical >=95% target, and all **60** controls have zero alarms. All 460 lifecycles complete and pass the independent final native/report/packet audit. The preceding 100-case development has 70/70 timely faults and 30 alarm-free controls; it is not pooled into acceptance. Source is copied unchanged from development to validation.

| Condition | Timely <100 ms | Late | Miss/unverified | P95 ms |
|---|---:|---:|---:|---:|
| high_businessloss | 60/60 | 0 | 0 | 55.875 |
| high_selective | 60/60 | 0 | 0 | 56.064 |
| wide_businessloss | 60/60 | 0 | 0 | 61.192 |
| wide_idle | 60/60 | 0 | 0 | 62.595 |
| wide_sparse_selective | 60/60 | 0 | 0 | 64.856 |
| wide_selective | 60/60 | 0 | 0 | 63.211 |
| wide_reorder80 | 20/20 | 0 | 0 | 52.990 |
| wide_processing80 | 20/20 | 0 | 0 | 54.553 |

All six weak conditions use 0.5% persistent loss: 80 Mb/s or 1 Gb/s selective network/application loss, 1 Mb/s selective loss, and business-idle size-independent loss. Severe network/application delay adds 80 ms to 25% of packets. The six controls retain nominal traffic, a business source pause, 10%-capacity competing traffic, dense and sparse 40 ms network delay, and 40 ms application delay. This is an empirical fraction result; 60/60 has a two-sided Wilson 95% lower bound of 93.98%, and 20/20 of 83.89%, not a population lower bound of 95%.

The links here have **10 Gb/s** capacity. Probes match 1500-byte business packets and traverse the same modeled application handler at 35000 pps: nominal 420 Mb/s/path (4.2% of link capacity), versus the old 17.92 Mb/s budget. Actual 8715 packets charge 13,072,500 bytes/path/lifecycle, or 420 Mb/s over the 249 ms source interval. Probe bytes equal 525% of 80 Mb/s business bytes and 42% of 1 Gb/s business bytes; sparse/idle overhead is still larger relative to business. This intervention changes capacity, packet shape/treatment and observation budget. It does not repair the failed 100 Mb/s fixed-budget envelope. The independent 96-byte collector still costs 7.3728 Mb/s. Computation is synchronous inside discrete-event callbacks and its elapsed execution cost is not modeled.

**Matched algorithm attribution:** with exactly these delivered reports and costs, the frozen M12 shadow rule has 396/400 timely faults: selective 58/60 and application loss 58/60 at 80 Mb/s, all other fault conditions 60/60 or 20/20, and no false alarms. It also meets every per-condition 95% gate. The new rule improves four decisions; the target pass largely reflects the changed observations, not a demonstrated unique algorithmic advance. No algorithm novelty claim follows from this comparison.

Artifacts: `runs/m13_coverage_development_v1`, `runs/m13_coverage_validation_v1`, `logs/m13_coverage_validation_v1_final_audit.json`, `logs/m13_coverage_pipeline_state.json`; frozen source `m13_source_frozen_coverage_validation_v1`, native backend `m13d_backend`. IDs 67000–67099 and 68000–68459 are disjoint from every earlier campaign.

Historical TX compensation can briefly undershoot after a sudden pause. The registered idle scene pauses business at 40 ms and injects in 50–60 ms; simultaneous high-rate pause-plus-fault onset and arbitrary correlated faults are not validated. These limits do not alter the completed registered acceptance matrix.

## Causal traffic-compensating validation

The source policy reads only accepted business packets in the PREVIOUS closed 10 ms window. For current span h, it emits max(0, floor(25000*h/1s) - floor(previous_data*h/10ms)) evenly spaced 1500-byte probes. Startup 1–10 ms assumes no prior business. No receiver count, fault probability, injection time/location or future data enters this policy. It predicts opportunity from past traffic, so transient overshoot/lag is possible and every emitted packet is charged. Receiver gaps still wait at least 40 ms. Source/report/binary/image dependencies are frozen before independent validation; the detector never consumes the wave-audit exports or scorer truth.

Development has 130/130 timely faults and 30 alarm-free controls in 160 registrations. Only after exact final audit, unchanged source is copied into the 460-case primary validation (71000–71459).

| Condition | Timely <100 ms | Late | Miss/unverified | P95 ms | Matched M12 shadow timely |
|---|---:|---:|---:|---:|---:|
| wide_selective | 60/60 | 0 | 0 | 70.072 | 58/60 |
| wide_businessloss | 60/60 | 0 | 0 | 72.109 | 59/60 |
| wide_sparse_selective | 60/60 | 0 | 0 | 73.589 | 59/60 |
| wide_idle | 60/60 | 0 | 0 | 75.353 | 55/60 |
| high_selective | 60/60 | 0 | 0 | 58.697 | 60/60 |
| high_businessloss | 60/60 | 0 | 0 | 57.480 | 60/60 |
| wide_reorder80 | 20/20 | 0 | 0 | 54.524 | 20/20 |
| wide_processing80 | 20/20 | 0 | 0 | 54.334 | 20/20 |

The same-report shadow has 391/400 timely decisions; per-condition counts above separate the observation-policy intervention from the class-separated decision rule. Under the adaptive observation budget, the shadow's idle condition has 55/60 timely decisions, below the 95% gate, versus candidate 60/60. The guarded gap rule therefore supplies a target-relevant benefit here even though both rules pass the constant high-budget envelope. Neither comparison is a reproduction of SprayCheck.

| Business condition | Actual average probe Mb/s/path | Fraction of 10 Gb/s link |
|---|---:|---:|
| 80 Mb/s continuous | 223.181–223.181 | 2.232% |
| 1 Gb/s continuous | 10.843–10.843 | 0.108% |
| 1 Mb/s sparse | 299.036–299.036 | 2.990% |
| 80 Mb/s with 160 ms idle | 274.602–274.602 | 2.746% |

These rates use actual accepted probe bytes over the complete 249 ms source lifecycle, including startup and causal lag; they are not steady-state-only savings. With no previous data the nominal upper rate is 300 Mb/s/path (3% of link capacity). Continuous 1 Gb/s data emits 225 startup probes/path and no subsequent probes; continuous 80 Mb/s still incurs substantial probe-to-business overhead. Sparse/idle sensing is not free. All versions charge the separate 96-byte collector identically: 460.8 KB/lifecycle and 7.3728 Mb/s steady collection load. This source-budget policy is a cost intervention; no population timing guarantee or universal probe equivalence is inferred.

The 60 high-traffic controls use fresh 72000–72059 IDs: ten each nominal, pause, mild congestion, dense/sparse 40 ms network delay and 40 ms application delay at 1 Gb/s. All are alarm-free and independently audited. Their runner adds only a campaign option; science sources, policy, binary and all primary trial definitions are verified identical to the frozen primary runner. Deterministic nominal repeats are implementation checks, not stochastic population false-alarm evidence.

Independent adaptive primary audit verifies 2208000 report rows and 14112000 probes; high-traffic supplement verifies 288000 rows and 211128 probes. Every sampled counter/gap/age, encoded report, FIFO copy and probe emission is reconstructed from causal packet events. Native and report-only Python alarm records match exactly. Full packet/report data remain on otakotak, with thin local review artifacts.

Final verification: 308 Linux unit/integration checks pass; local macOS has 305 passes and three pre-existing platform skips. The M12 source/binary/dependencies remain hash-identical to their original registration. Artifacts: `runs/m13_adaptive_validation_v1`, `logs/m13_adaptive_validation_v1_final_audit.json`, `m13_source_frozen_adaptive_validation_v1`, `m13e_backend`; supplemental source `m13_source_frozen_adaptive_controls_v1`. The retained fixed-rate 10 Gb/s validation is a comparator, not part of the adaptive fault denominator.
