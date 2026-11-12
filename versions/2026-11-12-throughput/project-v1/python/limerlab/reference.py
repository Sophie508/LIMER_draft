"""Verify archival results without depending on either original repository."""
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile
from .paths import ROOT, read_json, sha


def verify(extract=None):
    record = read_json(ROOT / 'reference/index.json')
    bundle = ROOT / 'reference' / record['archive']
    if sha(bundle) != record['sha256']: raise ValueError('Reference bundle checksum changed')

    def unpack(destination):
        with zipfile.ZipFile(bundle) as archive:
            for name in archive.namelist():
                (destination / name).resolve().relative_to(destination.resolve())
            archive.extractall(destination)
        dataset = destination / record['root']
        result = subprocess.run([sys.executable, str(ROOT / 'tools/verify_reference.py'), str(dataset)],
                                capture_output=True, text=True, timeout=300)
        if result.returncode: raise RuntimeError(result.stderr + result.stdout)
        import json
        proof = json.loads(result.stdout)
        if proof['runs_verified'] != record['runs']: raise ValueError('Reference denominator changed')
        return proof
    if extract:
        destination = Path(extract).resolve()
        destination.mkdir(parents=True, exist_ok=False)
        return unpack(destination)
    with tempfile.TemporaryDirectory(prefix='limer-reference-') as directory:
        destination = Path(directory).resolve()
        destination.relative_to(Path(tempfile.gettempdir()).resolve())
        return unpack(destination)
