"""Simulation-only two-ended delivery deficit; no hidden fault inputs."""
from collections import defaultdict, deque


class EarlyDeliveryDetector:
    RULE_VERSION = "hybrid-early-v4"
    PERIOD_NS = 10_000_000
    GUARD_NS = 10_000_000
    WINDOW_NS = 100_000_000
    REPORT_TTL_NS = 200_000_000
    MIN_MISSING = 2
    FIELDS = frozenset(("path", "batch", "side", "count", "sample_t_ns", "arrival_t_ns"))

    def __init__(self):
        self.now_ns = -1
        self._pending = {}
        self._done = {}
        self._history = defaultdict(deque)
        self._armed = defaultdict(lambda: True)
        self._clean = defaultdict(int)
        self._latest = defaultdict(lambda: -1)
        self._previous_counts = {}
        self.unavailable_batches = 0
        self.invalid_batches = 0
        self.completed_batches = 0
        self.confirmations = 0

    @property
    def retained_batches(self):
        return len(self._pending) + len(self._done)

    def _interrupt(self, path):
        self._history[path].clear()
        self._clean[path] = 0
        self._previous_counts.pop(path,None)

    def advance(self, now_ns):
        if type(now_ns) is not int or now_ns < self.now_ns:
            raise ValueError("report arrival times must be nondecreasing integers")
        self.now_ns = now_ns
        expired = []
        for store in (self._pending, self._done):
            for key in list(store):
                if now_ns > (key[1] + 1) * self.PERIOD_NS + self.REPORT_TTL_NS:
                    if store is self._pending:
                        expired.append(dict(path=key[0], batch=key[1], status="unavailable"))
                        self.unavailable_batches += 1
                        self._interrupt(key[0])
                    del store[key]
        for history in self._history.values():
            while history and history[0][0] < now_ns - self.WINDOW_NS:
                history.popleft()
        return expired

    @staticmethod
    def _same(a, b):
        return all(a[k] == b[k] for k in a if k != "arrival_t_ns")

    def observe(self, report):
        if set(report) != self.FIELDS:
            raise ValueError("only independently observed counter report fields are allowed")
        if not isinstance(report["path"], str) or not report["path"]:
            raise ValueError("path must be an observable nonempty identifier")
        for field in ("batch", "count", "sample_t_ns", "arrival_t_ns"):
            if type(report[field]) is not int or report[field] < 0:
                raise ValueError("report counts, IDs and times must be nonnegative integers")
        if report["side"] not in ("tx", "rx"):
            raise ValueError("report side must be tx or rx")
        end = (report["batch"] + 1) * self.PERIOD_NS
        earliest = end + self.GUARD_NS
        if report["sample_t_ns"] != earliest or report["arrival_t_ns"] < report["sample_t_ns"]:
            raise ValueError("a report cannot precede its batch/guard or own observation")
        self.advance(report["arrival_t_ns"])
        if self.now_ns > end + self.REPORT_TTL_NS:
            # The observation arrived too late to use. It is never a zero RX.
            return None
        key = (report["path"], report["batch"])
        pair = self._done.get(key)
        if pair is None:
            pair = self._pending.setdefault(key, {})
        side = report["side"]
        if side in pair:
            if not self._same(pair[side], report):
                raise ValueError("conflicting duplicate counter report")
            return None
        pair[side] = dict(report)
        if len(pair) != 2:
            return None
        del self._pending[key]
        self._done[key] = pair
        path = key[0]
        tx, rx = pair["tx"]["count"], pair["rx"]["count"]
        self.completed_batches += 1
        if rx > tx:
            raise ValueError("simultaneous RX cannot exceed source acceptance")
        # A delayed old clean report cannot rearm a newer deficient episode.
        if key[1] <= self._latest[path]:
            return None
        if key[1] > self._latest[path] + 1:
            self._interrupt(path)
        self._latest[path] = key[1]
        previous = self._previous_counts.get(path)
        self._previous_counts[path] = (tx,rx)
        if previous is None:
            return None
        if tx < previous[0] or rx < previous[1]:
            raise ValueError("cumulative delivery counters must not regress")
        sent,received = tx-previous[0],rx-previous[1]
        severe = sent >= 32 and received * 5 <= sent * 3
        history = self._history[path]
        if not severe:
            history.clear()
            return None
        history.append((self.now_ns, sent-received, key[1]))
        if len(history) < 2:
            return None
        recent = list(history)[-2:]
        return dict(rule_version=self.RULE_VERSION, path=path,
                    decision_t_ns=self.now_ns, missing_packets=sum(r[1] for r in recent),
                    evidence_batches=[r[2] for r in recent],
                    claim="Observed delivery deficit under the declared guard; cause unresolved")
