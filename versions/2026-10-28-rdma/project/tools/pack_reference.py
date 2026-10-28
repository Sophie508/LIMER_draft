"""Create an immutable reference dataset, independent of runtime source layout."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''): h.update(block)
    return h.hexdigest()


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    a.out.mkdir(exist_ok=False, parents=True)
    archive = a.out / 'closed-loop-20261027.zip'
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=5, allowZip64=True) as z:
        for file in sorted(a.source.rglob('*')):
            if file.is_file(): z.write(file, 'reference-20261027/' + file.relative_to(a.source).as_posix())
    # The original evidence index remains byte-for-byte inside the bundle.
    record = dict(schema='limer-reference-v1', archive=archive.name, sha256=sha(archive), bytes=archive.stat().st_size,
                  root='reference-20261027', runs=53, primary=40, boundary=6, qualification=7,
                  evidence_index_sha256=sha(a.source / 'files.sha256.json'),
                  original_binary_sha256='baadeb2c092ff55d6a055be683448847c24461c9a118321509afa426276a55de')
    (a.out / 'index.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(record), flush=True)
