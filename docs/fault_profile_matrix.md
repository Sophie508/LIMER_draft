# Fault-profile matrix (replacing the underspecified "gray-loss matrix")

Advisor feedback flagged the earlier term "gray-loss matrix" as unclear. This
document replaces it with an explicit, discussable definition: every fault
profile is a named point in a parameter space, and nothing is called "gray"
without saying exactly which parameters are impaired.

## Dimensions

| Dimension | Values under consideration | Status in the harness |
|---|---|---|
| rate cap | 80% / 20% / 5% of the 100 Mbit link | 20 Mbit is the formal v1 point; 5 Mbit config ready |
| packet loss | 0 / 0.1% / 1% / 5% random | supported by the injector; 1% config ready |
| delay | +0 / +1 ms (base) / +10 ms | `fault_delay_ms` implemented; +10 ms config ready |
| queue depth | netem limit 1000 (current) / 100 / 50 packets | fixed at 1000 today, not yet a variable |
| direction | egress (current) / ingress / both | egress only today |
| duration | persistent / 100 ms transient / 1 s transient / periodic flap | persistent + 100 ms today |
| affected scope | one worker-fabric link (current) / ToR uplink / two links | single link today |
| onset | abrupt (current) / gradual ramp | abrupt only today |

## Named profiles with runnable configs

- **FP-R20** — 20 Mbit egress cap, persistent (the formal v1/v2 point).
- **FP-R5** — 5 Mbit egress cap: `configs/fault_profiles_v1/fp_r5_impact.json`
- **FP-L1** — full rate, 1% random loss: `configs/fault_profiles_v1/fp_l1_impact.json`
- **FP-D10** — full rate, +10 ms delay: `configs/fault_profiles_v1/fp_d10_impact.json`
- **FP-T100** — 100 ms transient cap (the formal AA5 point).

The three new profiles are declared as impact-only measurements (no detector,
no recovery) so each fault type's raw signature is characterized before any
detection claim is made about it.

## Open decisions before widening the matrix

1. Which impairment does "gray" primarily mean in the intended deployment:
   rate cap, random loss, added delay, or partial-flow damage (e.g. one ECMP
   hash bucket)? Partial-flow damage would need new injector capability.
2. Is egress-only degradation sufficient, or must ingress/bidirectional
   variants be covered?
3. Are ToR-uplink or fabric-wide faults in scope? They are the cases that
   separate localized rerouting from global failover most sharply.
4. Do gradual-onset (ramping) faults and periodic flapping matter for the
   target scenario?
