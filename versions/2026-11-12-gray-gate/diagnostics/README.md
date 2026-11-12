# Why the candidate can reject a useful relay

These are read-only diagnostics of accepted pilot traces. They did not change
the frozen candidate, registered conditions, or native experiment results.

The concrete counterexample is zero-loss sustained slowdown to 25% capacity at
24 ms. Direct recovery finishes the four-phase job in **82.403551 ms**; the
candidate stays on the original paths and finishes in **95.443573 ms**. The
candidate is **15.82% slower**. Both measurements exclude the same 1-ms launch
offset and both passed execution and observation audits.

## Evidence chain

| Question | Observation | What follows |
| --- | --- | --- |
| Why did the gate stay? | Its recorded source/helper forecasts repeatedly favor staying or fail the benefit margin. | Read the [decision audit](sustained25early-model-audit.md); this is a model issue, not evidence that switching had no value. |
| Is helper service understated? | A fixed 10-ms window can include a previous phase's barrier idle time while remaining work belongs to the new phase. | A phase-aware window is a plausible causal correction; [design and boundaries](phase-service-design.md). |
| Would that correction alone change decisions? | Rebuilding all 28 reports and replaying 14 decisions gives **zero switch/stay flips**. | Helper-window repair alone is insufficient in this trace; [shadow replay](helper-window-shadow.md). |
| Does one probe describe the pipeline? | In the accepted direct arm, single-probe estimates are 1.645–2.750 Gb/s, while data completed during the fixed first 4 ms averages 4.639–5.562 Gb/s. | Concurrent chunks can have a higher aggregate service rate than one chunk's latency quotient; [calibration](relay-probe-calibration.md). |
| Can the observed rate simply replace the estimate? | Startup can be slower; paid ACKs lag physical completion; helper workload changes between probing and activation. | No. This is neither a same-state candidate counterfactual nor permission to multiply the estimate by a fitted constant. |

## Proposed next experiment, not an implemented result

Change the observation mechanism so it measures both startup and overlapping
relay service, with a fixed paid train of eight 64-KiB chunks. Keep the four
physical credits, shared source window of 32, helper contention, and every
probe/report/confirmation cost. Report phase-scoped helper and source service
without subtracting any within-phase stall. The full proposal and required
evidence fields are in the calibration and phase-service design notes.

Expected observation: the pipeline estimate should agree more closely with
subsequent delivered service, and fewer beneficial sustained-slowdown routes
should be rejected. Added probing can also erase that benefit for short jobs or
transient faults. Both outcomes must remain visible. First compare prediction
error and then whole-job completion against the same direct-recovery control.

This is a hypothesis for a separately frozen source and preregistered campaign.
No performance improvement from that proposal has been measured. It is not part
of the current `benefit_v2` implementation or its confirmation results.

## Replay and provenance

- [Helper-window reproduction instructions](helper-window-shadow-usage.md)
  and [receipt](helper-window-shadow-reproduction.json).
- [Relay extraction program](relay_probe_calibration.py),
  [reproduction receipt](relay-probe-calibration-reproduction.json), and
  [checksums](relay-probe-calibration.sha256). Its input guard restricts it to
  the exact accepted run and rejects 34 changed or unaccepted input variants.
- Both programs stream the retained raw archive on otakotak. They do not launch
  the simulator or modify original inputs. Raw archive/member checksums and
  the compact derivations are recorded in their receipts.
