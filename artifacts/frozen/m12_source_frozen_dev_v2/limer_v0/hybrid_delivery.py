"""Native-replayed delivery detection; no fault metadata enters either lane."""
from limer_v0.batch_loss import BatchLossDetector
from limer_v0.early_delivery import EarlyDeliveryDetector


class MatureDeliveryDetector(BatchLossDetector):
    RULE_VERSION = "hybrid-delivery-v2"


class HybridDeliveryDetector:
    RULE_VERSION = "hybrid-combined-v2"
    FIELDS = BatchLossDetector.FIELDS | {"guard_ns"}

    def __init__(self):
        self.early = EarlyDeliveryDetector()
        self.mature = MatureDeliveryDetector()
        self.alarmed = set()

    def advance(self, now_ns):
        return self.early.advance(now_ns) + self.mature.advance(now_ns)

    def observe(self, report):
        if set(report) != self.FIELDS or type(report["guard_ns"]) is not int:
            raise ValueError("only observed report fields and integer guard are allowed")
        row = {k:v for k,v in report.items() if k != "guard_ns"}
        guard = report["guard_ns"]
        if row["side"] == "tx" and guard == 0:
            candidates = (self.early.observe(row), self.mature.observe(row))
        elif row["side"] == "rx" and guard in (10_000_000, 50_000_000):
            target = self.early if guard == 10_000_000 else self.mature
            candidates = (target.observe(row),)
        else:
            raise ValueError("guard does not identify a valid measurement lane")
        # The report FIFO is globally chronological; advance both lane clocks.
        self.advance(row["arrival_t_ns"])
        for alarm in candidates:
            if alarm and alarm["path"] not in self.alarmed:
                self.alarmed.add(alarm["path"])
                return alarm
        return None

    @property
    def now_ns(self): return max(self.early.now_ns,self.mature.now_ns)

    @property
    def completed_batches(self): return self.early.completed_batches+self.mature.completed_batches

    @property
    def unavailable_batches(self): return self.early.unavailable_batches+self.mature.unavailable_batches

    @property
    def invalid_batches(self): return self.early.invalid_batches+self.mature.invalid_batches

    @property
    def retained_batches(self): return self.early.retained_batches+self.mature.retained_batches
