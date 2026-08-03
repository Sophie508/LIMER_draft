# Pre-registration: active_active_v2 step-level detection campaign

Registered 2026-08-03, before any formal v2 run is executed. Motivated by the
independent audit of the v1 results (see the 2026-08-03 next-stage audit): the
legacy detector's frozen median lands on the idle mode of the bimodal switch
trace, so a capped-but-flowing fault stays invisible until the port goes
silent (~2.78 s), and the round-level host gate cannot decide before the
degraded round completes.

## What changed in the stack

1. `BurstAwareSentinelRule` (`limer_v0/sentinel.py`): separates burst windows
   (> 1 Mbit noise floor) from gap windows, calibrates the baseline median on
   burst windows only, and raises SWITCH_SUSPECT after two consecutive
   degraded bursts, or after a gap run three times longer than anything seen
   in calibration (hard-failure path).
2. `STEP_DONE` telemetry (`limer_v0/worker.py`, flag `--step-telemetry`):
   workers stream per-step completions.
3. `StepGateRefiner` + `StepGateMonitor` (`limer_v0/refiner.py`,
   `limer_v0/orchestrator.py`, config `host_gate: "step"`): host confirmation
   fires mid-round after two distinct slow steps (> 1.5x the fault-free step
   p95) complete **while the switch-side degraded-burst symptom is still
   active**. That persistence condition is what separates a persistent fault
   from a transient: the preserved AA5 traces show a transient inflates just
   as many steps, but its switch symptom clears first. Commit still happens
   at the round boundary; mid-round cutover is explicitly out of scope here.

## Offline validation already performed (preserved v1 evidence, read-only)

Replayed via `scripts/replay_sentinel.py` and locked in
`tests/test_sentinel_burst.py` against the 21 archived formal runs:

- burst rule trigger: 34.9-45.9 ms after fault on all 12 detector runs
  (legacy: 2775-2786 ms); zero pre-fault or healthy-run triggers.
- reconstructed step gate: confirm at ~892 ms on every persistent-fault run;
  no-confirm on all three AA5 transients (slow steps 7, confirmable 0).

## Scenarios and predeclared gates (3 repeats each, failed repeats preserved)

| Scenario | Config | Gates (beyond the shared complete/correctness/operstate/isolation gates) |
|---|---|---|
| AA6_STEPDETECT | `configs/active_active_v2/aa6_stepdetect.json` | switch suspicion < 200 ms; fault-to-confirm < 1500 ms; host gate_mode step; exactly three worker-2 slots move; 20-round post-recovery retention median >= 0.9 |
| AA5_TRANSIENT (step stack) | `configs/active_active_v2/aa5_transient_stepstack.json` | host action suppress; no commit; retention within AA5 v1 gate |
| AA3_LOCAL (long window) | `configs/active_active_v2/aa3_local_longwindow.json` | unchanged AA3_LOCAL gates over a 20-round post-recovery window; reported alongside the per-round retention series to settle the drift question (v1 showed 0.978 -> 0.921 over three rounds) |

The AA6 latency gates are encoded in `limer_v0/report.py`
(`AA6_L_SWITCH_GATE_MS`, `AA6_L_DETECTION_GATE_MS`) so the aggregate report
enforces them mechanically. Predictions from offline replay: l_switch ~40 ms,
l_detection ~900 ms. The end-to-end fault-to-recovered-round time is NOT
expected to improve materially: the degraded round must still finish before
the round-boundary commit takes effect; removing that wait is the separate
step-boundary-cutover work item.

Honest scope notes:
- millisecond-level *commit* is achievable only for hard failures; for gray
  faults the confirm is impact-bounded (about one degraded step duration).
- results go to a fresh `results_active_active_v2_1/` directory; the v1 tree
  is immutable and its denominators are unchanged.

## Amendment 1 (2026-08-03, after the first pilot execution)

The first execution of this campaign (preserved unmodified at
`results_active_active_v2/` on the run host) exposed a design defect: the
step gate ran the alternate-path ping probe **mid-round**, while fabric B was
carrying the collective's own bulk traffic, so probe pings queued behind full
buffers (max 103 ms against a quiet-network limit of 4.1 ms) and every AA6
repeat deferred with "alternate fabric health probe failed". All three AA6
pilot repeats are kept as failed evidence; the AA5 and AA3_LOCAL long-window
runs in that directory are unaffected by the defect (their gates never reach
the mid-round probe).

Design change, registered before the corrected campaign:
- the mid-round probe now uses a loaded-network assessment (ping success plus
  a fixed 250 ms queueing allowance) and only answers "fabric B is reachable
  and not black-holed";
- the strict quiet-network criterion (2x idle baseline) is re-checked at the
  round boundary immediately before the handover; if it fails, the run defers
  and nothing commits. The safety bar in front of an actual route change is
  therefore identical to the v1 round gate.
- corrected campaign results go to `results_active_active_v2_1/`.

## Fault-profile impact configs (declared, not yet run)

`configs/fault_profiles_v1/`: FP-R5 (5 Mbit cap), FP-L1 (1 percent loss at
full rate), FP-D10 (10 ms delay), all AA1-style impact-only measurements on
worker 2's Fabric A egress. These parameterize the fault-profile matrix that
replaces the underspecified "gray-loss matrix"; the remaining dimensions
(direction, scope, ramp onset) need reviewer confirmation before further
implementation.

## How to run (Debian/Mininet host, root)

```
for rep in 01 02 03; do
  for cfg in aa6_stepdetect aa5_transient_stepstack aa3_local_longwindow; do
    scenario=$(python3 -c "import json;print(json.load(open('configs/active_active_v2/${cfg}.json'))['scenario_id'].lower())")
    python3 -m limer_v0.orchestrator \
      --config configs/active_active_v2/${cfg}.json \
      --results-dir results_active_active_v2 \
      --run-id ${scenario}_rep${rep}
  done
done
python3 -m limer_v0.report --results-dir results_active_active_v2
```
