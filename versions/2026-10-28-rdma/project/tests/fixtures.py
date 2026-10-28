import csv
import json

def base_relay_fixture(root):
    (root / 'inputs').mkdir()
    topology = ['92 4 4 72 32 A100', ' '.join(map(str, range(16, 92)))]
    for gpu in range(16):
        topology += [f'{gpu} {20 + gpu % 4} 10Gbps 0.0005ms 0', f'{gpu} {24 + gpu % 4} 10Gbps 0.0005ms 0']
    (root / 'inputs/topology.txt').write_text('\n'.join(topology) + '\n')
    logical, resources, legs, wire, control = [], [], [], [], []
    next_chunk = 0

    def event(t, name, c, epoch=0, ack=0, route=0):
        logical.append([t, name, c['id'], 0, c['src'], c['dst'], c['offset'], 65536, ack, epoch, c['lane'], route])

    def reserve(t, name, rid, c, relay=False, probe=False, length=65536):
        resources.append([t, name, rid, c['id'] if not probe else 0, 0, c['src'], c['dst'], 1 if relay else 0, 5 if relay else 0, c['lane'], int(relay), int(probe), length])

    def leg(t, rid, index, src, dst, nic, length, relay=False, probe=False):
        tag = rid * 10 + index
        legs.append([t, 'LEG_START', rid, tag, index, src, dst, nic, length])
        wire.append([t + 1, rid, tag, src, dst, nic, int(probe), int(relay), 0, length + 72, 0])
        legs.append([t + 10, 'LEG_DONE', rid, tag, index, src, dst, nic, length])
        return t + 10

    def chunk(src, dst, offset):
        nonlocal next_chunk
        next_chunk += 1
        return dict(id=next_chunk, src=src, dst=dst, offset=offset, lane=offset // 65536 % 2)

    t = 10
    # GPU1 and GPU5 both finish their own outgoing AND incoming work.
    for src, dst in [(1, 5), (5, 9), (12, 1)]:
        for offset in range(0, 1048576, 65536):
            c = chunk(src, dst, offset)
            rid = c['id']
            event(t, 'ALLOC', c)
            event(t, 'DIRECT_LAUNCH', c, route=rid)
            reserve(t, 'RESERVE', rid, c)
            end = leg(t, rid, 0, src, dst, c['lane'] + 2, 65536)
            event(end, 'ACK_PROGRESS', c, ack=65536, route=rid)
            event(end, 'DONE', c, ack=65536, route=rid)
            reserve(end, 'RELEASE', rid, c)
            t += 100
    # GPU0's preassigned A work finishes, while a B chunk remains.
    for offset in range(0, 1048576, 131072):
        c = chunk(0, 4, offset)
        rid = c['id']
        event(t, 'ALLOC', c)
        event(t, 'DIRECT_LAUNCH', c, route=rid)
        reserve(t, 'RESERVE', rid, c)
        end = leg(t, rid, 0, 0, 4, 2, 65536)
        event(end, 'ACK_PROGRESS', c, ack=65536, route=rid)
        event(end, 'DONE', c, ack=65536, route=rid)
        reserve(end, 'RELEASE', rid, c)
        t += 100
    c = chunk(0, 4, 65536)
    event(t, 'ALLOC', c)
    event(t, 'DIRECT_LAUNCH', c, route=c['id'])
    reserve(t, 'RESERVE', c['id'], c)
    tag = c['id'] * 10
    legs.append([t, 'LEG_START', c['id'], tag, 0, 0, 4, 3, 65536])
    wire.append([t + 1, c['id'], tag, 0, 4, 3, 0, 0, 0, 1048, 0])
    t += 1100000
    health = 900
    reserve(t, 'RESERVE', health, c, relay=True, probe=True, length=1024)
    for i, (s, d, nic) in enumerate([(0, 1, 1), (1, 5, 3), (5, 4, 1)]):
        t = leg(t, health, i, s, d, nic, 1024, relay=True, probe=True) + 1
    reserve(t, 'RELEASE', health, c, relay=True, probe=True, length=1024)
    t += 1000000
    control.append([t, t, 'ACTIVATE', 0, 0, 1, 0])
    legs.append([t, 'LEG_CANCEL', c['id'], tag, 0, 0, 4, 3, 65536])
    reserve(t, 'RELEASE', c['id'], c)
    event(t, 'MIGRATE', c, epoch=1)
    rid = 1000
    event(t, 'PROXY_LAUNCH', c, epoch=1, route=rid)
    reserve(t, 'RESERVE', rid, c, relay=True)
    for i, (s, d, nic) in enumerate([(0, 1, 1), (1, 5, 3), (5, 4, 1)]):
        t = leg(t, rid, i, s, d, nic, 65536, relay=True) + 1
    control.append([t, t + 1000000, 'FINAL_ACK', 0, 0, rid, 96])
    t += 1000000
    event(t, 'ACK_PROGRESS', c, epoch=1, ack=65536, route=rid)
    event(t, 'DONE', c, epoch=1, ack=65536, route=rid)
    reserve(t, 'RELEASE', rid, c, relay=True)
    tables = dict(
        logical_events=('timestamp_ns,event,chunk_id,phase,src,dst,offset,length,acked,epoch,lane,route', logical),
        peer_events=('timestamp_ns,event,route,chunk,phase,src,dst,helper_src,helper_dst,rail,relay,probe,length', resources),
        leg_events=('timestamp_ns,event,route,tag,index,src,dst,nic,length', legs),
        wire_events=('timestamp_ns,route,tag,src,dst,nic,probe,relay,sequence,wire_bytes,retransmission', wire),
        control_events=('sent_ns,arrival_ns,event,rank,phase,version,wire_bytes', control))
    for name, (header, data) in tables.items():
        with (root / (name + '.csv')).open('w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(header.split(','))
            writer.writerows(sorted(data, key=lambda r: r[0]))
    totals = dict(network_wire_bytes=0, local_wire_bytes=0, probe_wire_bytes=0,
                  relay_wire_bytes=0, retransmission_wire_bytes=0)
    for r in wire:
        totals['local_wire_bytes' if r[5] == 1 else 'network_wire_bytes'] += r[9]
        if r[6]: totals['probe_wire_bytes'] += r[9]
        if r[7] and not r[6]: totals['relay_wire_bytes'] += r[9]
    (root / 'run_status.json').write_text(json.dumps(dict(status='task_unfinished', method='G01-P',
        physical_planes=2, extra_rto=False, phases_expected=1, proxy_chunks=1, **totals)))

