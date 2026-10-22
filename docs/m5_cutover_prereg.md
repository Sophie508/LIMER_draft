# M5 cutover reliability pre-registration (2026-10-10)

Registered before the new regression and any new topology campaign.

## What changes and what we expect

Change: give each in-flight (round, step) one receive-attempt owner and retain
its partial frame reader across send-side cutover aborts on unchanged receive
routes. Replace it only after it has stopped when the receive route changes.

Prediction: a send failure followed by redo cannot consume a valid peer frame
in an abandoned receiver thread. The round finishes once, with zero checksum
and plan-version errors, one redo, and no extra send on an unchanged send route.
This prediction addresses a stream-reader race, not application-level loss.

## Evidence that motivates this amendment

Preserved failure: results_m4b_policy_v5/aa12_policy_switch/aa12_policy_rep03.
At round 3 step 2 rank 2 aborts a send with EBADF, rank 3 subsequently completes
step 2, but rank 2 buffers step 4 while still expecting step 2. The trace is
consistent with a receiver consuming the step-2 frame in an abandoned attempt.
It does not demonstrate a second packet drop on the healthy resend route.

## Local protocol

Use socketpairs, events and a controlled send-side exception; avoid random loss
and sleep-dependent synchronization. Start the first receiver, force send-side
cutover, deliver its expected frame, wait until that receiver consumes it, then
redo. The pre-repair code must time out; the repaired code must complete.
Also test a partial frame header spanning the abort, so restarting recv_frame
from the middle of a stream cannot pass as a correct fix.

Gates: no live duplicate reader on the same incoming socket; expected frame count;
one frame accounting entry per logical step; zero checksum/version errors;
unchanged-route send halves are preserved; corrupt frames and missing peers fail.

Run existing Python and JavaScript checks. Save before/after outputs outside
the public repository. Passing local tests does not resolve the Mininet campaign.

## Fresh remote regression (blocked until approved host is reachable)

Run 10 new lifecycles each for configs/m4b_policy/aa12_policy_switch.json and
aa12_policy_stay.json under results_m5_cutover/. Also run three lifecycles each
of AA7_HARD, AA8_GRAYFAST and AA5_TRANSIENT from active_active_v3.
Copy fixed source to a separate work directory in limer-mininet; never overwrite
archived evidence. Preserve all repeats, including worker failures.

Gates: switch 10/10 complete with one agreed fingerprint and zero correctness
errors; stay 10/10 suppress and complete; v3 gates unchanged. Report all raw
latencies and retention with denominators. A failure leaves the reliability
claim unresolved and requires a written amendment before a changed rerun.
