"""Phase boundary state transitions require independently logged evidence."""
import json
from pathlib import Path
import tempfile
import unittest
from test_audit import fixture,audit_module


class PhaseResetAuditTests(unittest.TestCase):
    def test_reset_log_required_in_phase_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);fixture(root)
            p=root/'run_status.json';value=json.loads(p.read_text())
            value.update(replacement_lifetime='phase',scope='phase-scoped B-prime replacement v3')
            p.write_text(json.dumps(value))
            (root/'phase_events.csv').write_text('timestamp_ns,event,phase\n1,PHASE,0\n')
            self.assertIn('missing phase binding reset',audit_module.audit(root)['errors'])
            p=root/'control_events.csv'
            resets=''.join('1,1,RESET_TO_AB,{},0,{},0\n'.format(i,i) for i in range(16))
            lines=p.read_text().splitlines();p.write_text(lines[0]+'\n'+resets+'\n'.join(lines[1:])+'\n')
            result=audit_module.audit(root)
            self.assertTrue(result['pass_'],result['errors'])

    def test_next_phase_cannot_reuse_previous_coordination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);fixture(root)
            p=root/'run_status.json';value=json.loads(p.read_text())
            value.update(replacement_lifetime='phase',scope='phase-scoped B-prime replacement v3')
            p.write_text(json.dumps(value))
            (root/'phase_events.csv').write_text('timestamp_ns,event,phase\n1,PHASE,0\n')
            p=root/'control_events.csv';lines=p.read_text().splitlines()
            resets=''.join('1,1,RESET_TO_AB,{},0,{},0\n'.format(i,i) for i in range(16))
            p.write_text(lines[0]+'\n'+resets+'\n'.join(lines[1:])+'\n')
            valid=audit_module.audit(root)
            self.assertTrue(valid['pass_'],valid['errors'])
            with p.open('a') as stream:
                stream.write('100000000,101000000,HELPER_READY,1,1,2,96\n')
                stream.write('100000000,101000000,HELPER_READY,5,1,2,96\n')
                stream.write('101000000,101000000,ACTIVATE,0,1,2,0\n')
            checked=audit_module.audit(root)
            self.assertIn('missing initial coordination participants',checked['errors'])
