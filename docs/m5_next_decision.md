# Contribution decision prepared for Sophie and advisor (2026-10-10)

## Decision

Recommended: prioritize finite-episode route-choice cost and localized execution
within two already-active planes. Keep quick gray-loss detection as an explicit
unmet constraint, not the principal demonstrated contribution. This is a proposal
for human/mentor agreement; it is not a new approved or validated method.

Alternative: retain <100ms gray-loss detection as the main contribution. This
requires a distinct signal and independent controls before the formal campaign;
the present per-socket retransmission observer is insufficient. Packet-spray
statistics cannot be transplanted to deterministic plane slots without a model.

## Concrete evidence motivating the choice

- Chameleon already provides adaptive failure-policy selection; avoid broad
  first-selector or non-ML novelty. Its node-failure strategy space differs from
  local network slots; this supports a candidate distinction, not a priority proof.
- Four independent matched OptCC network settings complete 30 total runs; published
  author integration/configs are missing, so exact paper figures are not recovered.
- Dual-plane static calibration changes its preferred route arm when B is slow:
  A40/B200 Gb/s favors switch(0.741 vs. 0.571 ms);A40/B20 favors stay (1.454 vs. 1.934 ms).
- With TCP 25% loss and B10 Mb/s, all three fixed-stay episodes timeout, all three fixed-switch
  episodes finish eight rounds (84.804–85.029 s), despite low spare. Expected stay is not
  an optimality label. Random loss and bandwidth degradation are distinct models.
- Observer first-delta ranges: 0.5% loss 44.5–1158.1 ms; 1% loss 59.4–157.4 ms; reordering produces
  hundreds of retransmissions. Nominal/control raw-counter behavior does not
  establish a detector. Rate-counter suspects occur in all 12 matched controls.
- Execution repair has 217 Linux unit checks and new transport correctness traces;
  numerical AllReduce/GPU training and switch-resident footprint remain unvalidated.

## Reviewable next pipeline if the recommendation is selected

1. Define the objective and inputs: finite work remaining, measured/imposed route
   service, coordination/redo costs, uncertainty. Do not label the current spare
   heuristic an optimal episode-cost selector or use injector truth as an input.
2. Register OptCC segmented-DAG plane assignment and background flow pacing.
   Match byte accounting and dependencies in ring/OptCC schedule factors; keep
   fixed stay, fixed localized switch and the new decision policy as separate arms.
3. Validate dynamic safe-boundary activation on four ranks before 16-rank scaling. Clearly
   separate imposed delay sweeps from implementation-measured control delay; keep
   packet loss, bandwidth degradation and hard faults in separate conditions.
4. Run preregistered matched scenes, retain timeout/censored arms and policy
   selection errors, then freeze evaluation claims before writing new advantages.
5. Add numerical reduction and GPU/NCCL/RDMA validation as a separately scoped
   resource decision if the paper requires production training claims.

The full 16-rank matrix, the new cost method and formal signal validation remain unrun.
Jev has no key and isoptional; no cloud enrollment or spending occurred.

## Human decision recorded (2026-10-10)

Sophie selected <100-ms detection as the primary research objective, while also
studying route-choice cost and execution correctness. Fast gray-failure detection
remains explicitly unresolved until prospective validation passes. The earlier
recommendation above was not selected. Continue with m6_detection_diagnostic_plan.md.
