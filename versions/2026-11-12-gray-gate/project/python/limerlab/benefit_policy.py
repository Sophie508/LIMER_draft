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


@dataclass
class HelperSample:
    """Paid endpoint report of its own outgoing workload, not remote truth."""
    own_remaining_bytes: int = 0
    own_bytes_per_ns: float = 0.0
    age_ns: int = 0
    known: bool = False


@dataclass
class BenefitInputV2(BenefitInput):
    b_no_progress_ns: int = 0
    tail_debounce_ns: int = 2_000_000
    source_window: int = 32
    pipelined: bool = True
    helpers: Tuple[HelperSample, HelperSample] = (None, None)


def evaluate_benefit_v2(x):
    """Local source/helper completion forecast, not a whole-job optimizer.

    Tail persistence uses elapsed time since the oldest unfinished B chunk's
    last progress. After the existing 2-ms observation cadence, that elapsed
    time is a forecast of another wait of similar duration, NOT a guaranteed
    bound on its future completion or knowledge of recovery time.

    Physical relay resources can be released before the final logical ACK.
    Data credits and the sender's confirmation window therefore constrain
    different cycles. A whole first relay/ACK cycle is always charged.

    A helper's observed own service forecasts its remaining work. Forwarding
    assigned bytes adds equal-byte opportunity cost to that helper while it
    has own work; this deliberately simple fluid model does not model all
    other ranks, tensor compute, or distinguish its A/B service headroom.
    """
    # Retain the original validator and original policy byte-for-byte above.
    evaluate_benefit(x)
    if any(type(v) is not int or v < 0 for v in
           (x.b_no_progress_ns, x.tail_debounce_ns, x.source_window)):
        raise ValueError('invalid v2 tail/window input')
    if not x.source_window or len(x.helpers) != 2:
        raise ValueError('v2 requires a positive sender window and two helpers')
    for h in x.helpers:
        if h is None:
            continue
        if (type(h.own_remaining_bytes) is not int or h.own_remaining_bytes < 0
                or type(h.age_ns) is not int or h.age_ns < 0
                or not math.isfinite(h.own_bytes_per_ns) or h.own_bytes_per_ns < 0):
            raise ValueError('invalid helper report')
    d = dict(should_switch=False, probe_required=False,
             reason='insufficient_service_evidence', stay_ns=math.inf,
             switch_ns=math.inf, gain_ns=0., relay_bytes_per_ns=0.,
             source_stay_ns=math.inf, source_switch_ns=math.inf,
             helper_stay_ns=math.inf, helper_switch_ns=math.inf,
             relay_assigned_bytes=0., tail_forecast_ns=0.)
    if x.a_bytes + x.b_bytes + x.pending_bytes == 0:
        d.update(reason='no_remaining_work', stay_ns=0., switch_ns=0.,
                 source_stay_ns=0., source_switch_ns=0.,
                 helper_stay_ns=0., helper_switch_ns=0.)
        return d
    if (not x.service_a.known or not x.service_b.known
            or x.service_a.age_ns > x.max_age_ns
            or x.service_b.age_ns > x.max_age_ns):
        return d
    source_stay = finish_time(x.a_bytes, x.b_bytes, x.pending_bytes,
                             x.service_a.bytes_per_ns, x.service_b.bytes_per_ns)
    tail = (float(x.b_no_progress_ns) if x.b_bytes and
            x.b_no_progress_ns >= x.tail_debounce_ns else 0.)
    source_stay = max(source_stay, tail)
    d.update(stay_ns=source_stay, source_stay_ns=source_stay,
             tail_forecast_ns=tail)
    if not x.helper_ready:
        d['reason'] = 'helpers_not_ready'
        return d
    if any(h is None or not h.known or h.age_ns > x.max_age_ns for h in x.helpers):
        d['reason'] = 'paid_helper_reports_required'
        return d
    helper_base = [h.own_remaining_bytes / h.own_bytes_per_ns
                   if h.own_remaining_bytes and h.own_bytes_per_ns > 0
                   else math.inf if h.own_remaining_bytes else 0.
                   for h in x.helpers]
    d['helper_stay_ns'] = max(helper_base)
    d['stay_ns'] = max(source_stay, d['helper_stay_ns'])
    if not math.isfinite(d['helper_stay_ns']):
        d['reason'] = 'helper_service_unresolved'
        return d
    if (not x.relay.known or x.relay.age_ns > x.max_age_ns
            or x.relay.sample_bytes < x.chunk_bytes or min(x.relay.leg_ns) <= 0):
        d.update(reason='representative_probe_required', probe_required=True)
        return d
    data_cycle = sum(x.relay.leg_ns)
    full_cycle = data_cycle + x.relay.final_ack_ns
    physical_cycle = data_cycle if x.pipelined else full_cycle
    relay_rate = min(x.chunk_bytes / max(x.relay.leg_ns),
                     x.relay.parallel_chunks * x.chunk_bytes / physical_cycle,
                     x.source_window * x.chunk_bytes / full_cycle)
    startup = max(0., full_cycle - x.chunk_bytes / relay_rate)
    source_change = finish_time(x.a_bytes, x.b_bytes, x.pending_bytes,
                                x.service_a.bytes_per_ns, relay_rate,
                                x.setup_ns + startup)
    if x.b_bytes:
        source_change = max(source_change, x.setup_ns + full_cycle)
    a_free = max(0., source_change * x.service_a.bytes_per_ns - x.a_bytes)
    relay_work = x.b_bytes + max(0., x.pending_bytes - a_free)
    helper_change = max(base + relay_work / h.own_bytes_per_ns
                        if h.own_remaining_bytes else 0.
                        for base, h in zip(helper_base, x.helpers))
    change = max(source_change, helper_change)
    stay = d['stay_ns']
    gain = stay - change if math.isfinite(change) else 0.
    threshold = max(x.min_gain_ns, x.min_gain_fraction * stay)
    switch = math.isfinite(change) and (not math.isfinite(stay) or gain > threshold)
    d.update(switch_ns=change, gain_ns=gain, relay_bytes_per_ns=relay_rate,
             source_switch_ns=source_change, helper_switch_ns=helper_change,
             relay_assigned_bytes=relay_work, should_switch=switch,
             reason='predicted_benefit_v2' if switch else
             ('benefit_below_margin' if gain > 0 else 'stay_no_slower'))
    return d
