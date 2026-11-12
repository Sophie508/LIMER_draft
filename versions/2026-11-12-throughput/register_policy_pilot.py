"""Register the supplementary frozen-v2 gate diagnostic for reproduction."""
import argparse
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'project/tools'))
from throughput_campaign import plan, resolve_build, sha, tree_hashes, ROOT, write_json


def register(build, out):
    record, _, _ = resolve_build(build)
    p = plan('pilot')
    p['schema'] = 'limer-throughput-policy-pilot-v2'
    p['role'] = 'Supplementary paired gate diagnostic; not a throughput acceptance cohort'
    p['changes'] = 'Only policy changes from always to benefit on the frozen v2 pipelined shared-helper code'
    p['expectation'] = ('The old estimator may reject useful early shared-helper recovery '
                        'because its latency/credit model is still conservative; measure '
                        'any regression rather than assume gate compatibility')
    p['cases'] = [case for case in p['cases']
                  if case['scene']['family'] in ('blackhole','weak_loss')]
    for case in p['cases']:
        case['scene']['policy'] = 'benefit'
        case['name'] = case['name'].replace('-always-', '-benefit-')
    p['run_count'] = len(p['cases'])
    p.update(build=str(build.resolve()), build_sha256=sha(build/'build.json'),
             binary_sha256=record['binary_sha256'],
             source_hashes={d: tree_hashes(ROOT/d) for d in ('src','python','tools')})
    out.mkdir(parents=True, exist_ok=False)
    write_json(out/'registration.json', p)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    register(args.build, args.out)
