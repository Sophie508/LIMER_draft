"""Verify shipped compact receipts, source provenance and regenerated tables."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parent
PROJECT=ROOT.parent/'2026-10-28-rdma/project'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
e=ROOT/'evidence';manifest=json.loads((e/'COMPACT_MANIFEST.json').read_text())
for name,digest in manifest['files'].items():assert sha(e/name)==digest,name
build=json.loads((e/'native-build.json').read_text())
for name,digest in build['source_hashes'].items():assert sha(PROJECT/name)==digest,name
reports=[]
with tempfile.TemporaryDirectory() as tmp:
    for group in ('development-v1','lifetime-full-v1','gray-full-v1'):
        reg=json.loads((e/group/'registration.json').read_text());assert reg['binary_sha256']==build['binary_sha256']
        for folder,hashes in reg['source_hashes'].items():
            current={p.relative_to(PROJECT/folder).as_posix():sha(p) for p in (PROJECT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts}
            assert current==hashes,folder
        out=Path(tmp)/group
        subprocess.run([sys.executable,str(ROOT/'summarize.py'),str(e/group),'--scorer',str(PROJECT/'tools/research_campaign.py'),'--out',str(out)],check=True)
        reread=json.loads((out/'report.json').read_text());expected=json.loads((ROOT/'results'/group/'report.json').read_text())
        assert reread==expected,group;reports.append(reread)
        for row in reread['rows']:
            status=json.loads((e/group/'runs'/row['name']/'run_status.json').read_text())
            # An unfinished job resets only phases actually entered.
            started=status['phases_done']+(status['status']!='completed')
            if row['lifetime']=='phase':assert row['phase_resets']==16*started
            if row['name'] in ('full-ring-blackhole-G11-always','full-ring-blackhole-G11-benefit'):
                assert row['fresh_Bprime_done']==762 and row['fresh_Bprime_phases']==28
                for phase in row['binding_lifecycles']:
                    assert phase['B_new_bytes']>0 and phase['reset_to_AB_ns'] is not None
                    if phase['activation_ns'] is not None:assert phase['first_B_allocation_ns']<phase['activation_ns']
            if row['method']=='A_ONLY':assert all(x.get('B_new_bytes',0)==0 and x.get('Bprime_new_bytes',0)==0 for x in row['binding_lifecycles'])
rows=[x for r in reports for x in r['rows']]
assert len(rows)==41 and all(x['valid'] for x in rows)
assert sum(x['status']=='completed' for x in rows)==36
archive=json.loads((ROOT/'verification/archive-integrity-final.json').read_text())
assert archive['registered_archives']==41 and archive['all_archive_hashes_rechecked']
receipt=dict(compact_files_verified=len(manifest['files']),native_source_files_match_build=len(build['source_hashes']),
    local_source_matches_registrations=True,table_replay_matches=True,registered_runs=41,execution_valid=41,
    communication_completed=36,unfinished_jobs_retained=5,original_B_reallocated_each_phase_verified=True,
    fresh_Bprime_payload_and_completion_verified=True,A_ONLY_business_verified=True,archived_packet_runs_hash_rechecked_on_server=41,
    scope='Local compact integrity and table re-derivation; retained server raw-replay/hash receipts. No raw packet replay on this laptop.')
(ROOT/'verification/final-check.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt,indent=2))
