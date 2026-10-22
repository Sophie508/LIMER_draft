# Idle-window policy amendment — 2026-10-10

> Execution uses the previously approved autonomous workflow; no commit/push.

**Goal:** Validate an opt-in conservative reference for alternate-plane headroom
without replacing the original live-window policy or its failed branch evidence.

**Architecture:** Freeze both faulted demand and surviving spare estimates after
healthy calibration. At policy time, baseline_guarded mode uses the smaller of
known current and baseline spare. If current spare is unknown after an idle
window, use the known baseline spare. An unknown baseline remains unknown and
selects stay; a missing current measurement is not evidence of increased capacity.

**Assumption:** Backup capacity and healthy offered demand remain stationary
through the episode. Extra observed load may decrease estimated spare. An idle
counter cannot detect an unobserved capacity decrease; the existing reachability
probe is required but cannot establish bandwidth. This is a bounded stationary
model, not a general solution to capacity inference.

**Change/expectation before execution:** Add optional policy_headroom_mode,
with live as the unchanged default and baseline_guarded as an explicit variant.
The new variant should preserve a calibrated switch opportunity through a >256
sample pause, retain stay when healthy spare is insufficient, and never manufacture
a spare estimate without calibration. Branch success and correctness are separate.

## Evidence and alternatives

Original otakotak r01 switch and stay both selected stay. Both POLICY_DECISION
records contain surviving spare_bps=null and 256 idle-window samples. The switch
trace confirms genuine step impact; the receive repair is not exercised there.
Do not tune the 1.25 reuse factor or burst floor from this observation.

Retaining only past line-rate estimates with current idle occupancy could invent
free capacity when the fault pauses the collective; freezing only the last known
spare leaves no guard against new load. Use a frozen spare ceiling with a current
lower estimate. The original heuristic's measurement uncertainty remains.

## Implementation and verification

- Add a pure guarded-headroom helper in orchestrator.py; preserve both input
  snapshots and reference assumption in policy metrics.
- Validate mode and reject non-default use outside host_gate=policy.
- Freeze the surviving estimate with the existing demand baseline. Record both
  snapshots in SWITCH_BASELINE_FROZEN for reproducible replay.
- Tests: calibrated idle fallback, lower live spare, higher live spare ceiling,
  unknown baseline, no input mutation, configuration mode compatibility.
- Run source suite, then copy to a new versioned remote source directory. The
  ongoing original campaign keeps its source snapshot and configurations.
- First run one switch and one stay lifecycle with baseline_guarded enabled;
  preserve failures and raw timing. Expand to 10 each only if branch, correctness
  and fingerprint gates all pass. No timing equivalence to historical VM claims.

## Early stop of the original branch campaign

Before launching additional lifecycles, the first switch POLICY_DECISION was
verified as stay with an unknown alternate spare. This already fails the
registered switch-branch gate. Finish and preserve the two active original r01
lifecycles, cancel the other 27 queued launches as unrun, and retain the full
registration with explicit cancellation reasons. Do not report a 29-run success
denominator or silently replace r01. Resume the nine original v3 lifecycle
checks and the new guarded pilot using separate names/source snapshots.
