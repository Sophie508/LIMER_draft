"""Generate the owned dual-plane topology and path-independent transport config."""
from pathlib import Path
from .paths import ROOT, sha, write_json


def generate(destination, scene):
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    lines = (ROOT / 'configs/topologies/dual_plane_16gpu.txt').read_text(encoding='utf-8').splitlines()
    for i in range(2, len(lines)):
        fields = lines[i].split()
        if int(fields[0]) < 16 and 16 <= int(fields[1]) < 20:
            fields[2] = str(scene.local_gbps) + 'Gbps'
            lines[i] = ' '.join(fields)
    (destination / 'topology.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    (destination / 'flow.txt').write_text('0\n')
    (destination / 'trace.txt').write_text('0\n')
    text = (ROOT / 'configs/transport.conf').read_text(encoding='utf-8')
    text = text.replace('${RUN_DIR}', destination.as_posix())
    if '${' in text: raise ValueError('Unexpanded transport configuration variable')
    (destination / 'config.txt').write_text(text, encoding='utf-8')
    write_json(destination / 'input_manifest.json', dict(world_size=16, gpus_per_server=4,
        physical_planes=2, access_gbps=10, local_gbps=scene.local_gbps,
        hashes={p.name: sha(p) for p in destination.iterdir() if p.is_file()}))


def inject(destination, scene):
    destination = Path(destination)
    destination.mkdir(exist_ok=False)
    fraction, loss = ((.25, 0) if scene.family == 'quarter' else
                      (1, .005) if scene.family == 'weak_loss' else (1, 1))
    nodes = range(4) if scene.family == 'no_idle_helpers' else [scene.node]
    end = min(scene.horizon_ns, scene.fault_ns + scene.fault_duration_ns) if scene.fault_duration_ns else scene.horizon_ns
    delay = 80000000 if scene.family == 'delay' else 0
    if delay: fraction, loss = 1, 0
    text = '' if scene.family == 'healthy' else ''.join(
        f'{scene.fault_ns} {end} {node} {fraction} {loss} {scene.seed+node} {delay}\n' for node in nodes)
    (destination / 'injection.txt').write_text(text)
