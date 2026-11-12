"""Tampered early release and uncharged helper lending must fail audit."""
import csv
import json
from pathlib import Path
import tempfile
import unittest
from test_audit import fixture,audit_module


class PipelineAuditTests(unittest.TestCase):
    def test_early_release_needs_actual_last_leg(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);fixture(root)
            p=root/'run_status.json';s=json.loads(p.read_text());s['relay_completion']='pipelined';p.write_text(json.dumps(s))
            checked=audit_module.audit(root)
            self.assertIn('pipelined release differs from final target delivery',checked['errors'])
            with (root/'leg_events.csv').open() as f:legs=list(csv.DictReader(f))
            delivered=next(int(x['timestamp_ns']) for x in legs if x['route']=='1000' and x['index']=='2' and x['event']=='LEG_DONE')
            p=root/'peer_events.csv'
            with p.open() as f:r=csv.DictReader(f);names=r.fieldnames;events=list(r)
            for x in events:
                if x['route']=='1000' and x['event']=='RELEASE':x['timestamp_ns']=str(delivered)
            events.sort(key=lambda x:int(x['timestamp_ns']))
            with p.open('w') as f:w=csv.DictWriter(f,fieldnames=names);w.writeheader();w.writerows(events)
            checked=audit_module.audit(root);self.assertTrue(checked['pass_'],checked['errors'])
            # Final delivery is insufficient to declare logical completion.
            p=root/'control_events.csv';p.write_text('\n'.join(x for x in p.read_text().splitlines() if ',FINAL_ACK,' not in x)+'\n')
            self.assertIn('logical completion before final notification',audit_module.audit(root)['errors'])

    def test_shared_mode_cannot_skip_lending(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);fixture(root)
            p=root/'run_status.json';s=json.loads(p.read_text());s['helper_mode']='shared';p.write_text(json.dumps(s))
            self.assertIn('relay lacks delivered matching lending authorization',audit_module.audit(root)['errors'])


if __name__=='__main__':unittest.main()
