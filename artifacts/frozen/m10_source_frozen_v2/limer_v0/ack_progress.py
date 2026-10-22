"""Causal development rule for sender ACK service, independent of fault metadata."""
from dataclasses import dataclass, field
from statistics import median


@dataclass
class _Path:
    previous: dict | None = None
    calibration: list[float] = field(default_factory=list)
    reference: float | None = None
    slow_windows: int = 0
    alarmed: bool = False


class AckProgressRule:
    """One alarm after three busy windows below half a four-window reference.

    This identifies degraded ACK progress after observed calibration. Idle or
    initially impaired paths do not acquire an external healthy reference.
    """

    SCHEMA = {'path', 'acked_bytes', 'sample_ns', 'arrival_ns', 'full_busy'}

    def __init__(self):
        self.paths = {}
        self.last_arrival = -1

    def observe(self, report):
        if set(report) != self.SCHEMA:
            raise ValueError('unexpected observation schema')
        for key in ('path', 'acked_bytes', 'sample_ns', 'arrival_ns'):
            if type(report[key]) is not int or report[key] < 0:
                raise ValueError('invalid observation field')
        if type(report['full_busy']) is not bool:
            raise ValueError('invalid busy flag')
        if report['arrival_ns'] < report['sample_ns'] or report['arrival_ns'] < self.last_arrival:
            raise ValueError('noncausal report arrival')
        state = self.paths.setdefault(report['path'], _Path())
        previous = state.previous
        if previous is not None:
            if report['sample_ns'] <= previous['sample_ns']:
                raise ValueError('out-of-order sample')
            if report['acked_bytes'] < previous['acked_bytes']:
                raise ValueError('acknowledgment counter decreased')
        self.last_arrival = report['arrival_ns']
        state.previous = dict(report)
        if previous is None:
            return None
        if not report['full_busy']:
            state.slow_windows = 0
            return None
        rate = ((report['acked_bytes'] - previous['acked_bytes']) /
                (report['sample_ns'] - previous['sample_ns']))
        if state.reference is None:
            if rate > 0:
                state.calibration.append(rate)
                if len(state.calibration) == 4:
                    state.reference = median(state.calibration)
            return None
        state.slow_windows = state.slow_windows + 1 if rate < state.reference/2 else 0
        if state.slow_windows >= 3 and not state.alarmed:
            state.alarmed = True
            return dict(path=report['path'], decision_ns=report['arrival_ns'])
        return None
