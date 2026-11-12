"""Copy compact new-project validation evidence; keep raw archives separate."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''): h.update(block)
    return h.hexdigest()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--campaign', type=Path, required=True)
    parser.add_argument('--regression', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    a = parser.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    for name in ['build.json', 'build.log']: shutil.copyfile(a.build / name, a.out / name)
    shutil.copyfile(a.regression, a.out / 'regression.json')
    for name in ['registration.json', 'results.json', 'campaign_state.json', 'summary.csv', 'summary.json', 'report.md']:
        shutil.copyfile(a.campaign / name, a.out / name)
    shutil.copytree(a.campaign / 'tooling', a.out / 'tooling', ignore=shutil.ignore_patterns('__pycache__'))
    for folder in sorted((a.campaign / 'runs').iterdir()):
        destination = a.out / 'runs' / folder.name
        destination.mkdir(parents=True)
        for file in folder.iterdir():
            if file.is_file() and file.name not in ['logical_events.csv', 'packet_events.csv', 'wire_events.csv', 'observations.jsonl']:
                shutil.copyfile(file, destination / file.name)
        for name in ['inputs', 'truth']: shutil.copytree(folder / name, destination / name)
    manifest = {p.relative_to(a.out).as_posix(): sha(p) for p in sorted(a.out.rglob('*')) if p.is_file()}
    (a.out / 'files.sha256.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(dict(files=len(manifest), raw_archives_included=False, destination=str(a.out))))
