"""Preregister a separate loss confirmation without changing native rules.

The inherited injector derives each directional RNG stream from seed + node.
Consecutive seeds can therefore reuse a stream. This prospective cohort keeps
the reference workload and parameters, spaces seeds by 32, and never pools the
old and new detection counts. Only the reference registration is read.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import random

from research_campaign import read_json, register


def confirmation_plan(reference, seed_base=103100000, seed_stride=32):
    if type(seed_base) is not int or seed_base < 0:
        raise ValueError('seed_base must be a nonnegative integer')
    if type(seed_stride) is not int or seed_stride < 16:
        raise ValueError('seed_stride must separate all 16 possible node offsets')
    source = reference['plan']
    selected = [deepcopy(c) for c in source['cases']
                if c['condition'] == 'weak_loss' and c['arm'] == 'benefit'
                and c['detector'] == 'service']
    if len(selected) != 60 or {c['trial'] for c in selected} != set(range(60)):
        raise ValueError('Reference must contain exactly 60 service/benefit loss trials')
    previous = {c['scene']['seed'] + c['scene']['node'] for c in source['cases']}
    derived = set()
    for case in selected:
        seed = seed_base + case['trial'] * seed_stride
        rng = random.Random(seed)
        node, onset = rng.randrange(16), rng.randint(35_000_000, 55_000_000)
        stream_pair = seed + node
        if stream_pair in previous or stream_pair in derived:
            raise ValueError('Confirmation reuses a reference or confirmation loss stream')
        derived.add(stream_pair)
        case['scene'].update(seed=seed, node=node, fault_ns=onset)
    plan = deepcopy(source)
    plan.update(name='Independent loss-stream confirmation of frozen service detector',
                cases=selected)
    plan['scoring'].update(primary_conditions=['weak_loss'], seed_base=seed_base,
                           seed_stride=seed_stride,
                           seed_formula='seed_base + trial * seed_stride; node/onset from Random(seed)',
                           unique_derived_loss_stream_pairs=60)
    plan['supplement'] = dict(reference_plan_sha256=reference['plan_sha256'],
        reason='Inherited injector uses seed+node; adjacent scene seeds can reuse loss streams.',
        unchanged='Native implementation, detector parameters, policy and workload.',
        interpretation='Separate prospective confirmation; never pool with reference loss detection counts.')
    return plan


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--seed-base', type=int, default=103100000)
    parser.add_argument('--seed-stride', type=int, default=32)
    args = parser.parse_args()
    reference = read_json(args.reference / 'registration.json')
    print(json.dumps(register(confirmation_plan(reference, args.seed_base, args.seed_stride),
                              args.build, args.out)))
