"""Verify exported evidence links to frozen source, inputs, tools and outcomes."""
import argparse
import hashlib
import json
from pathlib import Path


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--allow-partial', action='store_true')
    a = parser.parse_args()
    root = a.root
    read = lambda p: json.loads(p.read_text(encoding='utf-8'))
    index = read(root / 'files.sha256.json')
    for rel, digest in index.items():
        assert sha(root / rel) == digest, rel
    evidence = root / 'evidence'
    build = read(evidence / 'joint_build.json')
    for name in ['LimerClosedLoopPeer.cc', 'rdma-hw-peer.cc']:
        assert sha(evidence / 'compiled_source' / name) == build['source_hashes'][name], name
    analysis = read(root / 'analysis.json')
    if not a.allow_partial:
        assert analysis['complete'] and analysis['matrix_completed'] == analysis['matrix_expected'] == 46
        assert read(evidence / 'qualification.json')['passed']
        check = read(evidence / 'matrix_unit_checks.json')
        assert check['passed'] and check['tests'] == 13
        assert check['log_sha256'] == sha(evidence / 'matrix_unit_tests.log')
        assert check['registration_sha256'] == sha(evidence / 'matrix_registration.json')
    count = 0
    for prefix in ['smoke', 'matrix']:
        path = evidence / (prefix + '_registration.json')
        if not path.exists(): continue
        registration = read(path)
        assert registration['binary_sha256'] == build['binary_sha256']
        assert registration['build_sha256'] == sha(evidence / 'joint_build.json')
        for rel, digest in registration['tooling_hashes'].items():
            assert sha(evidence / (prefix + '_tooling') / rel) == digest, rel
        results_path = evidence / (prefix + '_results.json')
        results = read(results_path) if results_path.exists() else []
        expected = {t['name']: t for t in registration['cases']}
        assert len(results) == len({r['name'] for r in results})
        for r in results:
            assert all(r[k] == expected[r['name']][k] for k in ['method', 'scene', 'family'])
            assert r['audit']['pass'] and r['observation_audit']['pass']
            assert r['archive']['all_content_hashes_verified']
            directory = evidence / (prefix + '_runs') / r['name']
            manifest = read(directory / 'run_manifest.json')
            assert manifest['scene'] == r['scene']
            assert manifest['binary_sha256'] == build['binary_sha256']
            assert manifest['registration_sha256'] == sha(path)
            for rel, digest in manifest['input_hashes'].items():
                assert sha(directory / rel) == digest, rel
            for name, key in [('audit.json', 'audit'), ('observation_audit.json', 'observation_audit'),
                              ('performance.json', 'performance'), ('run_status.json', 'status')]:
                assert read(directory / name) == r[key]
            for file in directory.rglob('*'):
                if not file.is_file(): continue
                rel = str(file.relative_to(directory)).replace('\\', '/')
                if rel in r['archive']['files']:
                    assert sha(file) == r['archive']['files'][rel], rel
            count += 1
    print(json.dumps(dict(files_verified=len(index), runs_verified=count,
                         compiled_source_and_frozen_tooling_verified=True, complete=analysis['complete'])))


if __name__ == '__main__':
    main()
