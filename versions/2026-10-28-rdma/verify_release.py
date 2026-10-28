"""Verify the version manifest and optionally unpack its compact evidence.

No network, native experiment, or raw-archive verification is performed here.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parent


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            digest.update(block)
    return digest.hexdigest()


def child(root, relative):
    path = (root / relative).resolve()
    path.relative_to(root.resolve())
    return path


def verify():
    manifest = json.loads((ROOT / 'FILES.sha256.json').read_text())
    for relative, expected in manifest['files'].items():
        path = child(ROOT, relative)
        if not path.is_file() or sha(path) != expected:
            raise ValueError('Missing or changed release file: ' + relative)
    print(json.dumps({'release_files_verified': len(manifest['files']),
                      'scope': 'release content hashes; not raw experiment archives'}))


def unpack():
    destination = ROOT / 'project/research_evidence'
    if destination.exists():
        raise FileExistsError('Evidence destination already exists: ' + str(destination))
    assets = json.loads((ROOT / 'evidence/archive-index.json').read_text())
    with tempfile.TemporaryDirectory(prefix='.unpack-', dir=destination.parent) as temporary:
        temporary = Path(temporary)
        seen = set()
        for asset in assets:
            archive = child(ROOT, asset['path'])
            if sha(archive) != asset['sha256']:
                raise ValueError('Changed compact archive: ' + asset['path'])
            count = 0
            with tarfile.open(archive, 'r|gz') as stream:
                for member in stream:
                    if not member.isfile() or member.name in seen:
                        raise ValueError('Unexpected archive entry: ' + member.name)
                    relative = Path(member.name)
                    if relative.is_absolute() or relative.parts[0] != asset['campaign']:
                        raise ValueError('Unexpected campaign path: ' + member.name)
                    target = child(temporary, member.name)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with stream.extractfile(member) as source, target.open('xb') as output:
                        shutil.copyfileobj(source, output, length=1048576)
                    seen.add(member.name)
                    count += 1
            if count != asset['members']:
                raise ValueError('Compact archive member inventory changed')
        shutil.copytree(ROOT / 'evidence/verification', temporary / 'verification')
        shutil.copyfile(ROOT / 'evidence/README.compact-source.md', temporary / 'README.md')
        temporary.rename(destination)
    print(json.dumps({'compact_evidence_unpacked': str(destination)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--unpack-evidence', action='store_true')
    args = parser.parse_args()
    verify()
    if args.unpack_evidence:
        unpack()
