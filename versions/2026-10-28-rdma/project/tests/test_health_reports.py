"""Counterexamples for using remote health before the source learned it."""
import csv
import json
from pathlib import Path
import tempfile
import unittest

from limerlab.audit import audit
from test_audit import fixture as legacy_fixture


def load(root, name):
    with (root/(name+'.csv')).open() as stream:
        reader=csv.DictReader(stream)
        return reader.fieldnames,list(reader)


def save(root, name, columns, data):
    timestamp='sent_ns' if name=='control_events' else 'timestamp_ns'
    with (root/(name+'.csv')).open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=columns)
        writer.writeheader()
        writer.writerows(sorted(data,key=lambda row:int(row[timestamp])))


def update_totals(root):
    path=root/'run_status.json'
    status=json.loads(path.read_text())
    for key in ('network_wire_bytes','local_wire_bytes','probe_wire_bytes',
                'relay_wire_bytes','retransmission_wire_bytes'):
        status[key]=0
    _,wire=load(root,'wire_events')
    for row in wire:
        size=int(row['wire_bytes'])
        status['local_wire_bytes' if row['nic']=='1' else 'network_wire_bytes']+=size
        if row['probe']=='1':status['probe_wire_bytes']+=size
        if row['relay']=='1' and row['probe']=='0':status['relay_wire_bytes']+=size
        if row['retransmission']=='1':status['retransmission_wire_bytes']+=size
    _,control=load(root,'control_events')
    status['control_wire_bytes']=sum(int(row['wire_bytes']) for row in control)
    path.write_text(json.dumps(status))


def fixture(root):
    legacy_fixture(root)
    columns,control=load(root,'control_events')
    first_prepare=min(int(row['sent_ns']) for row in control if row['event']=='PREPARE')
    # Leave time for the charged health report before beginning coordination.
    for name in ('logical_events','peer_events','leg_events','wire_events','control_events'):
        cols,data=load(root,name)
        for row in data:
            for key in ('timestamp_ns','sent_ns','arrival_ns'):
                if key in row and int(row[key])>=first_prepare:
                    row[key]=str(int(row[key])+1_000_000)
            if name=='peer_events' and row['route']=='900':row['length']='65536'
            if name=='leg_events' and row['route']=='900':row['length']='65536'
            if name=='wire_events' and row['route']=='900':row['wire_bytes']=str(65536+72)
        save(root,name,cols,data)
    _,legs=load(root,'leg_events')
    measured=max(int(row['timestamp_ns']) for row in legs if row['route']=='900' and row['event']=='LEG_DONE')
    columns,control=load(root,'control_events')
    control.append(dict(sent_ns=str(measured),arrival_ns=str(measured+1_007_680),
                        event='HEALTH_REPORT',rank='0',phase='0',version='900',wire_bytes='96'))
    save(root,'control_events',columns,control)
    path=root/'run_status.json'
    status=json.loads(path.read_text())
    status.update(detector_mode='service',policy_mode='always',
                  scope='service-driven persistent B-prime replacement v2')
    path.write_text(json.dumps(status))
    update_totals(root)


class HealthReportAuditTests(unittest.TestCase):
    def check(self,mutation=None):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            fixture(root)
            result=audit(root)
            self.assertTrue(result['pass_'],result['errors'])
            if mutation:
                mutation(root)
                update_totals(root)
                result=audit(root)
                self.assertFalse(result['pass_'],result)
                self.assertTrue(any('health' in error for error in result['errors']),result)

    def report_mutation(self,root,change):
        columns,data=load(root,'control_events')
        change(next(row for row in data if row['event']=='HEALTH_REPORT'))
        save(root,'control_events',columns,data)

    def test_valid_service_always_report(self):self.check()

    def test_report_to_other_source_cannot_authorize_launch(self):
        self.check(lambda root:self.report_mutation(root,lambda row:row.update(rank='1')))

    def test_report_from_other_phase_cannot_authorize_launch(self):
        self.check(lambda root:self.report_mutation(root,lambda row:row.update(phase='1')))

    def test_report_arriving_after_launch_cannot_authorize_it(self):
        def mutate(root):
            _,logical=load(root,'logical_events')
            launch=max(int(row['timestamp_ns']) for row in logical if row['event']=='PROXY_LAUNCH')
            self.report_mutation(root,lambda row:row.update(arrival_ns=str(launch+1)))
        self.check(mutate)

    def test_report_sent_before_measurement_cannot_authorize_launch(self):
        self.check(lambda root:self.report_mutation(root,lambda row:row.update(sent_ns=str(int(row['sent_ns'])-1))))

    def test_unpaid_report_cannot_authorize_launch(self):
        self.check(lambda root:self.report_mutation(root,lambda row:row.update(wire_bytes='0')))

    def test_missing_report_cannot_authorize_launch(self):
        def mutate(root):
            columns,data=load(root,'control_events')
            save(root,'control_events',columns,[row for row in data if row['event']!='HEALTH_REPORT'])
        self.check(mutate)

    def test_later_unconsumed_cross_phase_report_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            fixture(root)
            for name in ('peer_events','leg_events','wire_events'):
                columns,data=load(root,name)
                extra=[]
                for row in data:
                    if row['route']!='900':continue
                    copied=dict(row)
                    copied['route']='901'
                    copied['timestamp_ns']=str(int(copied['timestamp_ns'])+20_000_000)
                    if 'tag' in copied:copied['tag']=str(int(copied['tag'])+100)
                    extra.append(copied)
                save(root,name,columns,data+extra)
            _,legs=load(root,'leg_events')
            measured=max(int(row['timestamp_ns']) for row in legs if row['route']=='901' and row['event']=='LEG_DONE')
            columns,control=load(root,'control_events')
            control.append(dict(sent_ns=str(measured),arrival_ns=str(measured+1_007_680),
                                event='HEALTH_REPORT',rank='0',phase='1',version='901',wire_bytes='96'))
            save(root,'control_events',columns,control)
            update_totals(root)
            checked=audit(root)
            self.assertTrue(checked['pass_'],checked['errors'])


if __name__=='__main__':unittest.main()
