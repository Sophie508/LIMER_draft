"""Declared OptCC byte reconstruction, graph validation and trace verification."""
import argparse
from collections import Counter, defaultdict, deque
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re


def validate(flows, p):
    ids = [f['id'] for f in flows]
    if len(ids) != len(set(ids)) or any(i <= 0 for i in ids):
        raise ValueError('Duplicate or nonpositive flow identity')
    index = {f['id']: f for f in flows}
    children = defaultdict(list)
    indegree = {}
    edges = Counter()
    for f in flows:
        if not 0 <= f['src'] < p or not 0 <= f['dst'] < p or f['src'] == f['dst']:
            raise ValueError('Invalid endpoint')
        if f['bytes'] <= 0:
            raise ValueError('Nonpositive payload')
        if len(f['deps']) != len(set(f['deps'])):
            raise ValueError('Duplicate dependency')
        indegree[f['id']] = len(f['deps'])
        for parent_id in f['deps']:
            if parent_id not in index:
                raise ValueError('Absent parent')
            parent = index[parent_id]
            if f['src'] == parent['src']:
                event = 'send'
            elif f['src'] == parent['dst']:
                event = 'recv'
            else:
                raise ValueError('Dependency requires a remote notification')
            children[parent_id].append(f['id'])
            edges[event] += 1
    queue = deque(i for i, degree in indegree.items() if degree == 0)
    visited = 0
    while queue:
        parent = queue.popleft()
        visited += 1
        for child in children[parent]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if visited != len(flows):
        raise ValueError('Cyclic graph')
    return dict(edges)


def convert_optcc(document, n_bytes, control_bytes=20):
    p, k, loss_factor = document['p'], document['k'], Fraction(str(document['L']))
    if p < 3 or k < 4 or k % 4 or loss_factor < 1 or n_bytes <= 0:
        raise ValueError('Invalid schedule parameters')
    section = (Fraction(n_bytes, k * (p - 1)) if loss_factor >= 2 else
               n_bytes * loss_factor / (k * ((p - 2) * loss_factor + 2)))
    result = []
    for original in document['flows']:
        f = dict(original, src=original['src'] - 1, dst=original['dst'] - 1)
        ty = f['type']
        control = ty == 'sync'
        if control:
            exact = Fraction(control_bytes)
        elif ty in ('bub_up', 'bub_dn'):
            exact = section * (2 - loss_factor) / loss_factor
        elif re.fullmatch(r'[ABCD]2(?:up|dn)', ty):
            exact = (2 * section / loss_factor if loss_factor < 2 and 0 < f['body'] < k
                     else section)
        elif re.fullmatch(r'(?:[ABCD][13]){1,2}', ty):
            exact = section * (len(ty) // 2)
        else:
            raise ValueError('Unsupported flow type: ' + ty)
        rounded = (2 * exact.numerator + exact.denominator) // (2 * exact.denominator)
        f.update(bytes=rounded, exact_bytes=str(exact), rounding_error=str(rounded - exact),
                 control=control)
        result.append(f)
    edges = validate(result, p)
    totals = defaultdict(lambda: {'data': 0, 'control': 0})
    for f in result:
        totals[str(f['src'])]['control' if f['control'] else 'data'] += f['bytes']
    return dict(mode='optcc_independent_reconstruction', p=p, k=k, L=str(loss_factor),
                N=n_bytes, control_bytes=control_bytes, section_bytes=str(section),
                dependency_events=edges, outgoing_bytes=dict(totals), flows=result)


def ring(p, n_bytes):
    if p < 2 or n_bytes <= 0 or n_bytes % p:
        raise ValueError('Ring requires positive exactly divisible tensor bytes')
    flows = []
    for step in range(2 * (p - 1)):
        for rank in range(p):
            # Each phase step depends on preceding local serialization and input arrival.
            deps = [] if step == 0 else [(step - 1) * p + rank + 1,
                                        (step - 1) * p + (rank - 1) % p + 1]
            flows.append(dict(id=step * p + rank + 1, src=rank, dst=(rank + 1) % p,
                              bytes=n_bytes // p, deps=deps, control=False))
    return dict(mode='ordinary_ring_network_only', p=p, N=n_bytes,
                dependency_events=validate(flows, p), flows=flows)


def save_graph(graph, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.dumps(graph, indent=2) + '\n'
    (output / 'graph.json').write_text(manifest)
    lines = [f"{graph['p']} {len(graph['flows'])}"]
    for f in graph['flows']:
        lines.append(' '.join(map(str, [f['id'], f['src'], f['dst'], f['bytes'],
                                        len(f['deps']), *f['deps']])))
    (output / 'graph.txt').write_text('\n'.join(lines) + '\n')
    return hashlib.sha256(manifest.encode()).hexdigest()


def verify_trace(graph, trace):
    events = {}
    for line in Path(trace).read_text().splitlines():
        event = json.loads(line)
        key = event['id'], event['event']
        if key in events:
            raise ValueError('Duplicate completion/launch: ' + str(key))
        events[key] = event['ns']
    index = {f['id']: f for f in graph['flows']}
    expected = {(i, ev) for i in index for ev in ('start', 'send', 'recv')}
    if set(events) != expected:
        raise ValueError(f'Incomplete/unexpected events: {len(set(events) ^ expected)}')
    for f in graph['flows']:
        fid = f['id']
        if not events[fid, 'start'] <= events[fid, 'send'] <= events[fid, 'recv']:
            raise ValueError('Invalid transport event order')
        for parent_id in f['deps']:
            event = 'send' if f['src'] == index[parent_id]['src'] else 'recv'
            if events[fid, 'start'] < events[parent_id, event]:
                raise ValueError('Premature dependency release')
    return dict(nodes=len(index), events=len(events), dependency_edges=sum(
        len(f['deps']) for f in graph['flows']), makespan_ns=max(events.values()),
        status='PASS')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['optcc', 'ring', 'verify'], required=True)
    parser.add_argument('--dag')
    parser.add_argument('--N', type=int)
    parser.add_argument('--p', type=int)
    parser.add_argument('--out')
    parser.add_argument('--trace')
    args = parser.parse_args()
    if args.mode == 'verify':
        print(json.dumps(verify_trace(json.loads(Path(args.dag).read_text()), args.trace)))
    else:
        graph = (convert_optcc(json.loads(Path(args.dag).read_text()), args.N) if
                 args.mode == 'optcc' else ring(args.p, args.N))
        print(save_graph(graph, args.out))


if __name__ == '__main__':
    main()
