"""Verified, streamed raw-evidence archives, with optional post-verification pruning."""
import hashlib
from pathlib import Path
import tarfile
from .paths import sha, write_json


def archive_run(source, destination, prune=False):
    source, destination = Path(source), Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists(): raise FileExistsError(destination)
    hashes = {p.relative_to(source).as_posix(): sha(p) for p in source.rglob('*') if p.is_file()}
    partial = destination.with_suffix('.partial')
    # Higher compression and removal of verified duplicate raw logs keep large
    # campaigns within account quotas; evidence content is unchanged.
    with tarfile.open(partial, 'w:gz', compresslevel=6) as archive:
        for rel in sorted(hashes): archive.add(source / rel, arcname=rel, recursive=False)
    seen = set()
    with tarfile.open(partial, 'r|gz') as archive:
        for member in archive:
            if not member.isfile(): continue
            digest = hashlib.sha256()
            with archive.extractfile(member) as stream:
                for block in iter(lambda: stream.read(1048576), b''): digest.update(block)
            if hashes.get(member.name) != digest.hexdigest(): raise ValueError('Archive mismatch: ' + member.name)
            seen.add(member.name)
    if seen != set(hashes): raise ValueError('Archive file inventory differs')
    partial.rename(destination)
    record = dict(archive=str(destination), sha256=sha(destination), bytes=destination.stat().st_size,
                  files=hashes, all_content_hashes_verified=True)
    write_json(source / 'archive_manifest.json', record)
    if prune:
        for name in ['wire_events.csv', 'packet_events.csv', 'observations.jsonl', 'logical_events.csv',
                     'leg_events.csv', 'peer_events.csv']:
            (source / name).unlink()
    return record
