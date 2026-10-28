"""Observable sender/phase completion heuristic; not a global optimizer.

All rates are bytes/ns. A zero recent service sample means no progress in
that observation window, not knowledge of the fault's future duration.
"""
from dataclasses import dataclass
import math
from typing import Tuple


@dataclass
class ServiceSample:
    bytes_per_ns: float = 0.0
    age_ns: int = 0
    known: bool = False


@dataclass
class RelaySample:
    sample_bytes: int = 0
    leg_ns: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    final_ack_ns: float = 0.0
    parallel_chunks: int = 4
    age_ns: int = 0
    known: bool = False


@dataclass
class BenefitInput:
    a_bytes: int
    b_bytes: int
    pending_bytes: int
    service_a: ServiceSample
    service_b: ServiceSample
    relay: RelaySample
    setup_ns: float = 0.0
    helper_ready: bool = True
    chunk_bytes: int = 65536
    max_age_ns: int = 20_000_000
    min_gain_ns: float = 1_000_000.0
    min_gain_fraction: float = 0.10


def finish_time(a_bytes, b_bytes, pending_bytes, rate_a, rate_b, delay_b=0.0):
    """Fluid completion bound with owned bytes and optimally split pending bytes.

    B service starts after delay_b; A can continue during coordination.
    The caller folds fixed-policy pending bytes into their owned A/B totals.
    This bound ignores other ranks' critical paths and future rate changes.
    """
    if (a_bytes and rate_a <= 0) or (b_bytes and rate_b <= 0):
        return math.inf
    lower = max(a_bytes / rate_a if a_bytes else 0.0,
                delay_b + b_bytes / rate_b if b_bytes else 0.0)
    if not pending_bytes:
        return lower
    if rate_a + rate_b <= 0:
        return math.inf

    def free_capacity(at):
        return (max(0.0, at * rate_a - a_bytes)
                + max(0.0, max(0.0, at - delay_b) * rate_b - b_bytes))

    upper = lower + delay_b + pending_bytes / (rate_a + rate_b) + 1.0
    while free_capacity(upper) < pending_bytes:
        upper = upper * 2.0 + 1.0
    for _ in range(80):
        mid = (lower + upper) / 2.0
        if free_capacity(mid) >= pending_bytes:
            upper = mid
        else:
            lower = mid
    return upper


def evaluate_benefit(x):
    """Return auditable stay/switch predictions without injected fault truth."""
    integer_values = (x.a_bytes, x.b_bytes, x.pending_bytes, x.chunk_bytes,
                      x.max_age_ns, x.service_a.age_ns, x.service_b.age_ns,
                      x.relay.age_ns, x.relay.sample_bytes,
                      x.relay.parallel_chunks)
    if any(type(v) is not int or v < 0 for v in integer_values):
        raise ValueError("invalid work, age, or probe sample")
    numeric_values = (x.setup_ns, x.min_gain_ns, x.min_gain_fraction,
                      x.service_a.bytes_per_ns, x.service_b.bytes_per_ns,
                      x.relay.final_ack_ns) + tuple(x.relay.leg_ns)
    if (not x.chunk_bytes or not x.relay.parallel_chunks
            or len(x.relay.leg_ns) != 3
            or any(not math.isfinite(v) or v < 0 for v in numeric_values)):
        raise ValueError("invalid service or control cost")
    result = dict(should_switch=False, probe_required=False,
                  reason="insufficient_service_evidence", stay_ns=math.inf,
                  switch_ns=math.inf, gain_ns=0.0, relay_bytes_per_ns=0.0)
    if x.a_bytes + x.b_bytes + x.pending_bytes == 0:
        result.update(reason="no_remaining_work", stay_ns=0.0, switch_ns=0.0)
        return result
    if (not x.service_a.known or not x.service_b.known
            or x.service_a.age_ns > x.max_age_ns
            or x.service_b.age_ns > x.max_age_ns):
        return result
    result["stay_ns"] = finish_time(x.a_bytes, x.b_bytes, x.pending_bytes,
                                    x.service_a.bytes_per_ns,
                                    x.service_b.bytes_per_ns)
    if not x.helper_ready:
        result["reason"] = "helpers_not_ready"
        return result
    if (not x.relay.known or x.relay.age_ns > x.max_age_ns
            or x.relay.sample_bytes < x.chunk_bytes
            or min(x.relay.leg_ns) <= 0):
        result.update(reason="representative_probe_required", probe_required=True)
        return result
    # No extrapolation from the old 1024-byte liveness-only probe. A complete
    # chunk sample includes all three store-and-forward legs. Credit limits
    # bound overlap; the longest shared leg bounds the pipeline's capacity.
    # Larger probes are allowed conservatively: do not scale their fixed
    # propagation/queueing latency down as if all elapsed time were bytes.
    legs = list(x.relay.leg_ns)
    cycle = sum(legs) + x.relay.final_ack_ns
    relay_rate = min(x.chunk_bytes / max(legs),
                     x.relay.parallel_chunks * x.chunk_bytes / cycle)
    # Aggregate overlap must not divide a single chunk's propagation and
    # final-ACK latency by the credit count. Charge pipeline fill once.
    startup = max(0.0, cycle - x.chunk_bytes / relay_rate)
    change = finish_time(x.a_bytes, x.b_bytes, x.pending_bytes,
                         x.service_a.bytes_per_ns, relay_rate,
                         x.setup_ns + startup)
    # Even a 144-byte rescued tail needs an entire first route/ACK cycle.
    # The single representative probe cannot identify fixed versus per-byte
    # latency, so retain its full measured cycle as a conservative lower
    # bound whenever B-owned work must use the candidate.
    if x.b_bytes:
        change = max(change, x.setup_ns + cycle)
    stay = result["stay_ns"]
    gain = stay - change if math.isfinite(change) else 0.0
    result.update(switch_ns=change, gain_ns=gain, relay_bytes_per_ns=relay_rate)
    threshold = max(x.min_gain_ns, x.min_gain_fraction * stay)
    should_switch = (math.isfinite(change) and
                     (not math.isfinite(stay) or gain > threshold))
    result.update(should_switch=should_switch,
                  reason="predicted_benefit" if should_switch else
                  ("benefit_below_margin" if gain > 0 else "stay_no_slower"))
    return result
