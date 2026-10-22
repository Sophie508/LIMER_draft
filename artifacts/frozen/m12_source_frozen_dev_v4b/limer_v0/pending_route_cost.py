"""Observable sender-service cost heuristic, not a DAG critical-path optimizer."""
import math


def pending_route_cost(pending_a, pending_b, inflight_a, inflight_b,
                       rate_a, rate_b, b_age_ns, coordination_ns=10_000):
    values = (pending_a,pending_b,inflight_a,inflight_b,coordination_ns)
    if any(type(v) is not int or v < 0 for v in values):
        raise ValueError('invalid remaining work or coordination cost')
    if (rate_a is None or rate_b is None or b_age_ns is None or
            not math.isfinite(rate_a) or not math.isfinite(rate_b) or
            rate_a <= 0 or rate_b <= 0 or b_age_ns < 0 or b_age_ns > 20_000_000):
        return dict(switch=False,reason='unknown_or_stale_service',stay_ns=None,switch_ns=None)
    stay = max((inflight_a+pending_a)/rate_a,(inflight_b+pending_b)/rate_b)
    change = max(inflight_a/rate_a,(inflight_b+pending_b+pending_a)/rate_b)+coordination_ns
    return dict(switch=pending_a > 0 and change < stay,reason='cost_comparison',
                stay_ns=stay,switch_ns=change)
