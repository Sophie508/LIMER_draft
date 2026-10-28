"""Explicit, validated case configuration shared by CLI and campaigns."""
from dataclasses import asdict, dataclass

METHODS = ('G00', 'G10', 'G01', 'G11')
SCENARIOS = ('healthy', 'quarter', 'weak_loss', 'blackhole', 'no_idle_helpers', 'slow_local', 'short_blackhole', 'delay')


@dataclass(frozen=True)
class Scenario:
    family: str = 'healthy'
    rounds: int = 2
    chunks_per_phase: int = 64
    horizon_ns: int = 2500000000
    fault_ns: int = 20000000
    node: int = 0
    seed: int = 100001
    local_gbps: int = 2400
    detector: str = 'legacy'
    policy: str = 'always'
    fault_duration_ns: int = 0
    canary_period_ns: int = 2000000
    canary_bytes: int = 65536

    def __post_init__(self):
        if self.family not in SCENARIOS: raise ValueError('Unknown scenario: ' + self.family)
        if self.rounds < 1: raise ValueError('rounds must be positive')
        if self.chunks_per_phase < 16 or self.chunks_per_phase % 2:
            raise ValueError('chunks_per_phase must be even and at least 16')
        if not 1000000 <= self.fault_ns < self.horizon_ns:
            raise ValueError('Require 1ms <= fault time < observation horizon')
        if not 0 <= self.node < 16 or self.seed < 0 or self.local_gbps <= 0:
            raise ValueError('Invalid node, random stream or local bandwidth')
        if self.detector not in ('legacy', 'service') or self.policy not in ('always', 'benefit'):
            raise ValueError('Unknown detector or replacement policy')
        if self.fault_duration_ns < 0 or self.canary_period_ns < 100000 or self.canary_bytes != 65536:
            raise ValueError('Invalid duration or representative canary geometry')

    def dictionary(self):
        return asdict(self)
