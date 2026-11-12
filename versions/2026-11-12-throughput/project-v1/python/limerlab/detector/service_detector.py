"""Endpoint-clock service detector; no injected fault fields are accepted.

The first observed calibration interval is assumed representative of health.
The maximum completed canary service time in that interval is then frozen.
v2 also counts sender-observed retransmissions on distinct canaries. This
measures transport repair cost/delivery risk, not unrecoverable packet loss.
v3 also accepts active business work's last sender-observed ACK progress time.
v4 accepts receiver whole-path, full-packet spacing windows computed exclusively
from past accepted packet arrivals. It measures dispersion, not isolated QP rate.
"""
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceDetectorConfig:
    calibration_ns: int = 20_000_000
    multiplier_num: int = 2
    multiplier_den: int = 1
    margin_ns: int = 100_000
    floor_ns: int = 100_000
    fallback_ns: int = 2_000_000
    window_ns: int = 40_000_000
    bad_samples: int = 3
    min_span_ns: int = 4_000_000
    business_stall_ns: int = 40_000_000
    spacing_window_ns: int = 10_000_000
    spacing_min_samples: int = 64
    spacing_multiplier_num: int = 2
    spacing_multiplier_den: int = 1
    spacing_margin_ns: int = 100
    spacing_bad_windows: int = 2
    spacing_packet_bytes: int = 976
    spacing_quantile_num: int = 1
    spacing_quantile_den: int = 10


class ServiceDetector:
    RULE_VERSION = "canary-service-v4"

    def __init__(self, config=None):
        self.config = config or ServiceDetectorConfig()
        c = self.config
        if (any(type(v) is not int for v in vars(c).values()) or
                c.calibration_ns < 0 or c.multiplier_num <= 0 or
                c.multiplier_den <= 0 or c.margin_ns < 0 or c.floor_ns <= 0 or
                c.fallback_ns <= 0 or c.window_ns <= 0 or c.bad_samples <= 0 or
                not 0 <= c.min_span_ns <= c.window_ns or c.business_stall_ns <= 0 or
                c.spacing_window_ns <= 0 or c.spacing_min_samples <= 0 or
                c.spacing_multiplier_num <= 0 or c.spacing_multiplier_den <= 0 or
                c.spacing_margin_ns < 0 or c.spacing_bad_windows <= 0 or c.spacing_packet_bytes <= 0 or
                c.spacing_quantile_den <= 0 or not 0 <= c.spacing_quantile_num < c.spacing_quantile_den):
            raise ValueError("invalid service detector configuration")
        self.now_ns = -1
        self.paths = {}
        self.alarms = []
        self.on_alarm = None

    @staticmethod
    def _natural(value):
        return type(value) is int and value >= 0

    def baseline_ns(self, path):
        return self.paths.get(path, {}).get("baseline", 0)

    def deadline_ns(self, path):
        c = self.config
        baseline = self.baseline_ns(path)
        if not baseline:
            return max(c.floor_ns, c.fallback_ns)
        scaled = (baseline * c.multiplier_num + c.multiplier_den - 1) // c.multiplier_den
        return max(c.floor_ns, scaled + c.margin_ns)

    def calibrated(self, path):
        return self.paths.get(path, {}).get("frozen", False)

    def alarmed(self, path):
        return self.paths.get(path, {}).get("alarmed", False)

    def spacing_baseline_ns(self, path):
        return self.paths.get(path, {}).get("spacing_baseline", 0)

    def pending_count(self, path):
        return len(self.paths.get(path, {}).get("pending", {}))

    def _evaluate(self, path, p):
        c = self.config
        while p["bad"] and p["bad"][0][0] < self.now_ns - c.window_ns:
            p["bad"].popleft()
        if p["alarmed"] or len(p["bad"]) < c.bad_samples:
            return None
        submissions = [b[1] for b in p["bad"]]
        if max(submissions) - min(submissions) < c.min_span_ns:
            return None
        p["alarmed"] = True
        alarm = dict(rule_version=self.RULE_VERSION, path=path,
                     decision_t_ns=self.now_ns, signal="canary_service",
                     baseline_ns=p["baseline"], deadline_ns=self.deadline_ns(path),
                     evidence_tokens=[b[2] for b in p["bad"]],
                     evidence_submitted_ns=submissions)
        self.alarms.append(alarm)
        if self.on_alarm:
            self.on_alarm(alarm)
        return alarm

    def advance(self, now_ns):
        if not self._natural(now_ns) or now_ns < self.now_ns:
            raise ValueError("nonmonotone service observation time")
        self.now_ns = now_ns
        emitted = []
        c = self.config
        for path in sorted(self.paths):
            p = self.paths[path]
            if not p["frozen"] and now_ns >= p["first"] + c.calibration_ns:
                p["frozen"] = True
            if not p["frozen"]:
                continue
            limit = self.deadline_ns(path)
            for token, sample in sorted(p["pending"].items()):
                if not sample["bad"] and now_ns - sample["submitted"] > limit:
                    sample["bad"] = True
                    p["bad"].append((now_ns, sample["submitted"], token))
            alarm = self._evaluate(path, p)
            if alarm:
                emitted.append(alarm)
        return emitted

    def submit(self, path, token, now_ns, payload_bytes):
        if not self._natural(path) or not self._natural(token) or not self._natural(payload_bytes) or not payload_bytes:
            raise ValueError("path/token must be nonnegative; payload must be positive")
        p = self.paths.get(path)
        if p and (token in p["tokens"] or payload_bytes != p["bytes"]):
            raise ValueError("duplicate canary token or changed payload size")
        emitted = self.advance(now_ns)
        if p is None:
            p = dict(first=now_ns, baseline=0, frozen=not self.config.calibration_ns,
                     alarmed=False, bytes=payload_bytes, tokens=set(), pending={}, bad=deque(),
                     spacing_baseline=0, spacing_last=-1, spacing_bad=deque())
            self.paths[path] = p
        p["tokens"].add(token)
        p["pending"][token] = dict(submitted=now_ns, bad=False)
        return emitted

    def complete(self, path, token, now_ns):
        if path not in self.paths or token not in self.paths[path]["pending"]:
            raise ValueError("unknown/completed canary token")
        emitted = self.advance(now_ns)
        p = self.paths[path]
        sample = p["pending"].pop(token)
        if not p["frozen"]:
            p["baseline"] = max(p["baseline"], now_ns - sample["submitted"])
        return emitted

    def retransmit(self, path, token, now_ns):
        if path not in self.paths or token not in self.paths[path]["pending"]:
            raise ValueError("unknown/completed canary token")
        emitted = self.advance(now_ns)
        p = self.paths[path]
        sample = p["pending"][token]
        if p["frozen"] and not sample["bad"]:
            sample["bad"] = True
            p["bad"].append((now_ns, sample["submitted"], token))
            alarm = self._evaluate(path, p)
            if alarm:
                emitted.append(alarm)
        return emitted

    def stall(self, path, token, now_ns, last_progress_ns, remaining_bytes):
        if path not in self.paths:
            raise ValueError("unknown business observation path")
        if (not self._natural(token) or not self._natural(last_progress_ns) or
                not self._natural(remaining_bytes) or last_progress_ns > now_ns):
            raise ValueError("invalid business ACK progress observation")
        emitted = self.advance(now_ns)
        p = self.paths[path]
        if (not p["frozen"] or p["alarmed"] or not remaining_bytes or
                now_ns - last_progress_ns < self.config.business_stall_ns):
            return emitted
        p["alarmed"] = True
        alarm = dict(rule_version=self.RULE_VERSION, path=path,
                     decision_t_ns=now_ns, signal="business_ack_stall",
                     baseline_ns=p["baseline"], deadline_ns=self.config.business_stall_ns,
                     evidence_tokens=[token], evidence_submitted_ns=[last_progress_ns])
        self.alarms.append(alarm)
        emitted.append(alarm)
        if self.on_alarm:
            self.on_alarm(alarm)
        return emitted

    def spacing(self, path, window_end_ns, p10_spacing_ns, sample_count):
        if path not in self.paths:
            raise ValueError("unknown receiver spacing path")
        p, c = self.paths[path], self.config
        expected = (p["first"] + c.calibration_ns if p["spacing_last"] < 0
                    else p["spacing_last"] + c.spacing_window_ns)
        if (not self._natural(window_end_ns) or not self._natural(p10_spacing_ns) or
                not self._natural(sample_count) or window_end_ns != expected or
                sample_count >= c.spacing_min_samples and not p10_spacing_ns):
            raise ValueError("invalid/missing receiver spacing window")
        emitted = self.advance(window_end_ns)
        calibration = p["spacing_last"] < 0
        p["spacing_last"] = window_end_ns
        if calibration:
            if sample_count >= c.spacing_min_samples:
                p["spacing_baseline"] = p10_spacing_ns
            return emitted
        if p["alarmed"] or not p["spacing_baseline"]:
            return emitted
        threshold = ((p["spacing_baseline"] * c.spacing_multiplier_num + c.spacing_multiplier_den - 1)
                     // c.spacing_multiplier_den + c.spacing_margin_ns)
        if sample_count < c.spacing_min_samples or p10_spacing_ns <= threshold:
            p["spacing_bad"].clear()
            return emitted
        p["spacing_bad"].append(window_end_ns)
        if len(p["spacing_bad"]) < c.spacing_bad_windows:
            return emitted
        p["alarmed"] = True
        alarm = dict(rule_version=self.RULE_VERSION, path=path,
                     decision_t_ns=window_end_ns, signal="delivery_spacing_shift",
                     baseline_ns=p["spacing_baseline"], deadline_ns=threshold,
                     evidence_tokens=list(p["spacing_bad"]),
                     evidence_submitted_ns=[end - c.spacing_window_ns for end in p["spacing_bad"]])
        self.alarms.append(alarm)
        emitted.append(alarm)
        if self.on_alarm:
            self.on_alarm(alarm)
        return emitted
