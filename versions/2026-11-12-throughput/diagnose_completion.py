"""Read retained logical events to identify which ranks set phase completion."""
import argparse
from collections import Counter
import codecs
import csv
import json
from pathlib import Path
from statistics import mean
import tarfile


def diagnose(run, archive):
    starts = {int(row['phase']): int(row['timestamp_ns'])
              for row in csv.DictReader((run / 'phase_events.csv').open())}
    ends, allocations, fresh = {}, {}, Counter()
    with tarfile.open(archive, 'r|gz') as stream:
        for member in stream:
            if member.name != 'logical_events.csv':
                continue
            with codecs.getreader('utf-8')(stream.extractfile(member)) as file:
                for row in csv.DictReader(file):
                    p, s = int(row['phase']), int(row['src'])
                    chunk = int(row['chunk_id'])
                    if row['event'] == 'ALLOC':
                        allocations[chunk] = int(row['epoch'])
                    elif row['event'] == 'DONE':
                        ends[p, s] = int(row['timestamp_ns'])
                        if allocations[chunk] == 1:
                            fresh[p, s] += 1
            break
    phases = list(range(3, len(starts)))
    assert phases and all((p, s) in ends for p in phases for s in range(16))
    critical = Counter(max(range(16), key=lambda s: ends[p, s]) for p in phases)
    per_rank = {}
    for s in range(16):
        times = [(ends[p, s] - starts[p]) / 1e6 for p in phases]
        per_rank[s] = dict(mean_outbound_complete_ms=mean(times),
                           min_ms=min(times), max_ms=max(times),
                           fresh_relay_chunks=sum(fresh[p, s] for p in phases),
                           critical_phase_count=critical[s])
    return dict(run=run.name, raw_archive=str(archive), phases=phases,
                metric='Time from phase start to each rank completing its own outgoing payload, including final notifications.',
                mean_phase_completion_ms=mean((max(ends[p,s] for s in range(16))-starts[p])/1e6 for p in phases),
                per_rank=per_rank)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('archive', type=Path)
    parser.add_argument('out', type=Path)
    args = parser.parse_args()
    args.out.write_text(json.dumps(diagnose(args.run, args.archive), indent=2)+'\n')
