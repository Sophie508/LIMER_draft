"""Create a single-project release ZIP with a complete content manifest."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''): h.update(block)
    return h.hexdigest()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT.parent / 'LIMER-Delivery-20261027.zip')
    a = parser.parse_args()
    destination = a.out.resolve()
    if destination.exists(): raise FileExistsError(destination)
    subprocess.run([sys.executable, str(ROOT / 'limer.py'), 'verify'], check=True)
    excluded = {'.git', '__pycache__', '.venv', 'dist', 'outputs', 'build'}
    files = [p for p in sorted(ROOT.rglob('*')) if p.is_file() and not any(x in excluded for x in p.relative_to(ROOT).parts)
             and p.suffix != '.pyc' and p.resolve() != destination and p != ROOT / 'DELIVERY_MANIFEST.json']
    hashes = {p.relative_to(ROOT).as_posix(): sha(p) for p in files}
    record = dict(schema='limer-delivery-v1', created_utc=datetime.now(timezone.utc).isoformat(),
                  files=hashes, project='LIMER', source_only=True, raw_experiment_archives_included=False)
    partial = destination.with_suffix('.partial.zip')
    with zipfile.ZipFile(partial, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=5, allowZip64=True) as archive:
        for p in files:
            mode = zipfile.ZIP_STORED if p.suffix.lower() in ['.zip', '.gz', '.png', '.pdf', '.jpg'] else zipfile.ZIP_DEFLATED
            archive.write(p, 'LIMER-Delivery/' + p.relative_to(ROOT).as_posix(), compress_type=mode)
        archive.writestr('LIMER-Delivery/DELIVERY_MANIFEST.json', json.dumps(record, indent=2).encode())
    with zipfile.ZipFile(partial) as archive:
        for name, digest in hashes.items():
            h = hashlib.sha256()
            with archive.open('LIMER-Delivery/' + name) as stream:
                for block in iter(lambda: stream.read(1048576), b''): h.update(block)
            if h.hexdigest() != digest: raise ValueError('Archive mismatch: ' + name)
        if json.loads(archive.read('LIMER-Delivery/DELIVERY_MANIFEST.json')) != record:
            raise ValueError('Delivery metadata mismatch')
    partial.rename(destination)
    digest = sha(destination)
    destination.with_suffix('.zip.sha256').write_text(digest + '  ' + destination.name + '\n')
    result = dict(archive=str(destination), bytes=destination.stat().st_size, files=len(files), sha256=digest,
                  all_archive_members_read_and_verified=True)
    destination.with_suffix('.release.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
