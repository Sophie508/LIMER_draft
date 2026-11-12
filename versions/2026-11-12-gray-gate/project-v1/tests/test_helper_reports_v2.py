"""Counterexamples for free, stale, or fabricated helper workload evidence."""
import csv
import json
from pathlib import Path
import tempfile
import unittest
from limerlab.audit import audit_helper_reports


def write_csv(path, columns, values):
    with path.open('w', newline='') as f:
        writer=csv.DictWriter(f,fieldnames=columns);writer.writeheader();writer.writerows(values)


def fixture(root):
    (root/'run_status.json').write_text(json.dumps(dict(chunks_per_phase=16,horizon_ns=40_000_000)))
    columns=['timestamp_ns','event','chunk_id','src','phase','acked']
    write_csv(root/'logical_events.csv',columns,[
        dict(zip(columns,[1_000_000,'ALLOC',10,1,0,0])),
        dict(zip(columns,[10_000_000,'ACK_PROGRESS',10,1,0,1000])),
        dict(zip(columns,[15_000_000,'ACK_PROGRESS',10,1,0,4000])),
        dict(zip(columns,[20_000_000,'ACK_PROGRESS',10,1,0,5000]))])
    columns=['sent_ns','arrival_ns','event','rank','phase','version','wire_bytes']
    entries=[(1_000_000,2_007_680,'LEND_TX',1,0,100,96),
             (1_007_680,2_015_360,'LEND_RX',5,0,100,96),
             (2_015_360,2_015_360,'LEND_ACTIVE',0,0,100,0),
             (3_000_000,3_000_000,'M13_REPLACEMENT_PREPARE',0,0,101,0),
             (18_992_320,20_000_000,'HELPER_QUERY_TX',1,0,102,96),
             (20_000_000,21_007_680,'HELPER_REPORT_TX',0,0,102,96)]
    write_csv(root/'control_events.csv',columns,[dict(zip(columns,x)) for x in entries])
    row=dict(event='SENT',timestamp_ns=20_000_000,source=0,slot=0,rank=1,phase=0,version=101,
             lease_id=100,report_id=102,sampled_ns=20_000_000,delivered_ns=21_007_680,
             own_remaining_bytes=16*65536-5000,own_bytes_per_ns=5000/10_000_000,known=True)
    write_reports(root,[row,dict(row,event='DELIVERED',timestamp_ns=row['delivered_ns'])])


def write_reports(root, records):
    (root/'helper_reports.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in records))


class HelperReportV2Tests(unittest.TestCase):
    def run_case(self, mutation=None, error=None):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);fixture(root)
            result=audit_helper_reports(root)
            self.assertTrue(result['pass_'],result)
            if mutation:
                mutation(root);result=audit_helper_reports(root)
                self.assertFalse(result['pass_'],result)
                if error:self.assertTrue(any(error in msg for msg in result['errors']),result)

    def mutate(self, root, change):
        data=[json.loads(x) for x in (root/'helper_reports.jsonl').read_text().splitlines()]
        change(data);write_reports(root,data)

    def controls(self, root, change):
        with (root/'control_events.csv').open() as f:
            reader=csv.DictReader(f);columns=reader.fieldnames;data=list(reader)
        change(data);write_csv(root/'control_events.csv',columns,data)

    def test_exact_ten_ms_boundary_is_included(self):self.run_case()

    def test_same_timestamp_before_ack_is_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);fixture(root)
            self.mutate(root,lambda data:[x.update(own_remaining_bytes=16*65536-4000,
                                                  own_bytes_per_ns=4000/10_000_000) for x in data])
            result=audit_helper_reports(root);self.assertTrue(result['pass_'],result)

    def test_cannot_mix_two_same_timestamp_prefixes(self):
        self.run_case(lambda root:self.mutate(root,lambda data:[x.update(own_remaining_bytes=16*65536-4000) for x in data]),'incompatible causal')

    def test_cannot_fabricate_remaining_bytes(self):
        self.run_case(lambda root:self.mutate(root,lambda data:[x.update(own_remaining_bytes=0) for x in data]),'remaining bytes')

    def test_cannot_use_later_progress_in_sample(self):
        self.run_case(lambda root:self.mutate(root,lambda data:[x.update(own_bytes_per_ns=1.25) for x in data]),'service')

    def test_cannot_change_payload_in_transit(self):
        self.run_case(lambda root:self.mutate(root,lambda data:data[1].update(own_remaining_bytes=0)),'in transit')

    def test_cannot_sample_before_query_arrival(self):
        self.run_case(lambda root:self.controls(root,lambda data:next(x for x in data if x['event']=='HELPER_QUERY_TX').update(arrival_ns='20000001')),'paid query')

    def test_cannot_omit_report_cost(self):
        self.run_case(lambda root:self.controls(root,lambda data:next(x for x in data if x['event']=='HELPER_REPORT_TX').update(wire_bytes='0')),'cost')

    def test_cannot_misaddress_report(self):
        self.run_case(lambda root:self.controls(root,lambda data:next(x for x in data if x['event']=='HELPER_REPORT_TX').update(rank='9')),'address')

    def test_cannot_consume_snapshot_after_phase_reset(self):
        self.run_case(lambda root:self.controls(root,lambda data:data.append(dict(sent_ns='20500000',arrival_ns='20500000',event='RESET_TO_AB',rank='0',phase='1',version='200',wire_bytes='0'))),'phase reset')

    def test_cannot_consume_released_lease_report(self):
        self.run_case(lambda root:self.controls(root,lambda data:data.append(dict(sent_ns='20500000',arrival_ns='20500000',event='LEND_RELEASED',rank='0',phase='0',version='100',wire_bytes='0'))),'released lease')

    def test_stale_callback_is_logged_but_not_consumed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);fixture(root)
            self.controls(root,lambda data:data.append(dict(sent_ns='20500000',arrival_ns='20500000',event='RESET_TO_AB',rank='0',phase='1',version='200',wire_bytes='0')))
            self.mutate(root,lambda data:data[1].update(event='STALE'))
            result=audit_helper_reports(root);self.assertTrue(result['pass_'],result)
            self.assertEqual((result['delivered'],result['stale']),(0,1))

if __name__=='__main__':unittest.main()
