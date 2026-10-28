"""Reject service evidence detached from real network completion and exposure."""
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from limerlab.service_replay import replay_service
from limerlab.detector.service_detector import ServiceDetector


def fixture(root,horizon=5000000):
    (root/'run_manifest.json').write_text(json.dumps(dict(scene=dict(horizon_ns=horizon,
        canary_bytes=65536,canary_period_ns=2000000))))
    (root/'run_status.json').write_text(json.dumps(dict(monitor_end_ns=horizon)))
    events=[];legs=[];token=0
    for t in range(1000000,horizon,2000000):
        events.append([t,'ADVANCE',0,0,0])
        for src in range(16):
            dst=src+4 if src<12 else (src+1)%4
            for rail in range(2):
                token+=1;path=(src*16+dst)*3+rail
                events.extend([[t,'SUBMIT',path,token,65536],[t+60000,'COMPLETE',path,token,65536]])
                legs.extend([[t,'LEG_START',token,token,0,src,dst,rail+2,65536],
                             [t+60000,'LEG_DONE',token,token,0,src,dst,rail+2,65536]])
    paths=[(src*16+(src+4 if src<12 else (src+1)%4))*3+rail
           for src in range(16) for rail in range(2)]
    events=[row+[0,0,0] for row in events]
    for end in range(21_000_000,horizon,10_000_000):
        for path in paths:events.append([end,'SPACING',path,end,0,0,0,0])
    for name,header,data in [('service_events.csv','timestamp_ns,event,path_id,token,bytes,last_progress_ns,spacing_ns,sample_count',events),
          ('leg_events.csv','timestamp_ns,event,route,tag,index,src,dst,nic,length',legs)]:
        with (root/name).open('w',newline='') as f:
            w=csv.writer(f);w.writerow(header.split(','));w.writerows(sorted(data,key=lambda r:r[0]))
    (root/'service_decisions.jsonl').write_text('')
    (root/'service_alarms.csv').write_text('timestamp_ns,path_id,signal\n')
    (root/'detector_events.csv').write_text('timestamp_ns,path_id,signal,alarm_origin\n')
    (root/'control_events.csv').write_text('sent_ns,arrival_ns,event,rank,phase,version,wire_bytes\n')
    (root/'wire_events.csv').write_text('timestamp_ns,route,tag,src,dst,nic,probe,relay,sequence,wire_bytes,retransmission\n')
    (root/'logical_events.csv').write_text('timestamp_ns,event,chunk_id,phase,src,dst,offset,length,acked,epoch,lane,route\n')
    (root/'packet_events.csv').write_text('timestamp_ns,event,path_id,probe,batch,sequence,attempt_or_port,offset,accepted,payload_bytes\n')


def packet_spacing_fixture(root, received, summaries, horizon=42_000_000):
    """Add manually specified packet times and independently expected windows."""
    fixture(root,horizon)
    packets=[]
    with (root/'leg_events.csv').open() as stream:
        reader=csv.DictReader(stream);columns=reader.fieldnames;legs=list(reader)
    for sequence,(time,payload) in enumerate(received):
        tag=1_000_000+sequence
        submitted=time-100
        offset=0 if payload==976 else 65536-payload
        legs.append(dict(timestamp_ns=submitted,event='LEG_START',route=tag,tag=tag,
                         index=0,src=0,dst=4,nic=3,length=65536))
        packets.extend([[submitted,'source_accept',13,0,submitted//10_000_000,sequence,tag,offset,1,payload],
                        [time,'network_rx',13,0,submitted//10_000_000,sequence,12000+sequence,offset,1,payload]])
    with (root/'leg_events.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=columns);writer.writeheader()
        writer.writerows(sorted(legs,key=lambda row:int(row['timestamp_ns'])))
    with (root/'packet_events.csv').open('w',newline='') as stream:
        writer=csv.writer(stream)
        writer.writerow('timestamp_ns,event,path_id,probe,batch,sequence,attempt_or_port,offset,accepted,payload_bytes'.split(','))
        writer.writerows(sorted(packets,key=lambda row:row[0]))
    with (root/'service_events.csv').open() as stream:
        reader=csv.DictReader(stream);columns=reader.fieldnames;events=list(reader)
    for row in events:
        if row['event']=='SPACING' and row['path_id']=='13':
            p10,count=summaries.get(int(row['token']),(0,0))
            row.update(spacing_ns=p10,sample_count=count)
    with (root/'service_events.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=columns);writer.writeheader();writer.writerows(events)


def boundary_spacing_fixture(root):
    # The gap whose current RX is exactly 21 ms belongs to the second
    # window. A 144-byte tail resets full-to-full eligibility. Previous RX
    # state survives both window boundaries.
    received=[(1_010_000,976),(1_011_000,976),(21_000_000,976),
              (21_001_000,976),(21_002_000,144),(21_003_000,976),
              (21_004_000,976),(31_000_000,976)]
    packet_spacing_fixture(root,received,{21_000_000:(1000,1),
        31_000_000:(1000,3),41_000_000:(9_996_000,1)})


class ServiceReplayTests(unittest.TestCase):
    def check_case(self, change=None):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);fixture(root)
            self.assertTrue(replay_service(root)['pass_'])
            if change:
                change(root)
                self.assertFalse(replay_service(root)['pass_'])
    def test_real_network_canaries_replay(self): self.check_case()
    def test_missing_physical_leg_rejected(self):
        self.check_case(lambda p:(p/'leg_events.csv').write_text((p/'leg_events.csv').read_text().splitlines()[0]+'\n'))
    def test_monitor_must_cover_registered_horizon(self):
        self.check_case(lambda p:(p/'run_status.json').write_text('{"monitor_end_ns":4000000}'))
    def test_missing_canary_schedule_rejected(self):
        self.check_case(lambda p:(p/'service_events.csv').write_text('timestamp_ns,event,path_id,token,bytes\n'))
    def test_unreported_alarm_rejected(self):
        self.check_case(lambda p:(p/'detector_events.csv').write_text('timestamp_ns,path_id,signal,alarm_origin\n4000000,13,canary_service,SERVICE-R\n'))
    def test_business_stall_must_match_real_ack_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);fixture(root,60000000)
            (root/'logical_events.csv').write_text('timestamp_ns,event,chunk_id,phase,src,dst,offset,length,acked,epoch,lane,route\n1000000,ALLOC,9999,0,0,4,0,65536,0,0,1,0\n')
            with (root/'service_events.csv').open() as f: data=list(csv.DictReader(f))
            data.append(dict(timestamp_ns='41000000',event='STALL',path_id='13',token='9999',bytes='65536',last_progress_ns='1000000',spacing_ns=0,sample_count=0))
            with (root/'service_events.csv').open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=['timestamp_ns','event','path_id','token','bytes','last_progress_ns','spacing_ns','sample_count']);w.writeheader();w.writerows(sorted(data,key=lambda r:int(r['timestamp_ns'])))
            (root/'service_decisions.jsonl').write_text(json.dumps(dict(rule_version=ServiceDetector.RULE_VERSION,signal='business_ack_stall',path=13,decision_t_ns=41000000,baseline_ns=60000,deadline_ns=40000000,tokens=[9999]))+'\n')
            (root/'control_events.csv').write_text('sent_ns,arrival_ns,event,rank,phase,version,wire_bytes\n41000000,42007680,SERVICE_ALARM,13,0,0,96\n')
            (root/'service_alarms.csv').write_text('timestamp_ns,path_id,signal\n42007680,13,business_ack_stall\n')
            (root/'detector_events.csv').write_text('timestamp_ns,path_id,signal,alarm_origin\n42007680,13,business_ack_stall,SERVICE-R\n')
            self.assertTrue(replay_service(root)['pass_'])
            with (root/'logical_events.csv').open('a') as f:
                f.write('20000000,ACK_PROGRESS,9999,0,0,4,0,65536,1024,0,1,0\n')
            self.assertFalse(replay_service(root)['pass_'])

    def spacing_case(self,change=None):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);boundary_spacing_fixture(root)
            checked=replay_service(root)
            self.assertTrue(checked['pass_'],checked['errors'])
            self.assertEqual(checked['spacing_summaries_reconstructed'],96)
            self.assertEqual(checked['source_packets_checked'],8)
            self.assertEqual(checked['accepted_packets_checked'],8)
            if change:
                change(root)
                checked=replay_service(root)
                self.assertFalse(checked['pass_'],checked)

    def test_raw_spacing_preserves_boundaries_cross_windows_and_short_tail(self):
        self.spacing_case()

    def test_spacing_p10_tamper_rejected(self):
        self.spacing_case(lambda root:(root/'service_events.csv').write_text(
            (root/'service_events.csv').read_text().replace('0,0,1000,3','0,0,1001,3')))

    def test_missing_spacing_summary_rejected(self):
        def change(root):
            path=root/'service_events.csv'
            path.write_text('\n'.join(line for line in path.read_text().splitlines()
                                      if ',SPACING,13,31000000,' not in line)+'\n')
        self.spacing_case(change)

    def test_rx_payload_must_match_source_acceptance(self):
        self.spacing_case(lambda root:(root/'packet_events.csv').write_text(
            (root/'packet_events.csv').read_text().replace('12000,0,1,976','12000,0,1,975')))

    def test_source_payload_must_match_physical_leg_offset(self):
        self.spacing_case(lambda root:(root/'packet_events.csv').write_text(
            (root/'packet_events.csv').read_text().replace('1000004,65392,1,144','1000004,65391,1,144')))

    def test_raw_payload_column_is_required(self):
        self.spacing_case(lambda root:(root/'packet_events.csv').write_text(
            (root/'packet_events.csv').read_text().replace(',payload_bytes','')))

    def test_nearest_rank_p10_uses_second_of_eleven_samples(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            times=[1_010_000]
            for gap in range(100,1200,100):times.append(times[-1]+gap)
            packet_spacing_fixture(root,[(time,976) for time in times],
                                   {21_000_000:(200,11)})
            checked=replay_service(root)
            self.assertTrue(checked['pass_'],checked['errors'])

    def test_raw_spacing_two_bad_windows_emit_charged_alarm(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            times=([1_010_000+i*1000 for i in range(65)]
                   +[21_000_000+i*3000 for i in range(65)]
                   +[31_000_000+i*3000 for i in range(65)])
            packet_spacing_fixture(root,[(time,976) for time in times],
                                   {21_000_000:(1000,64),31_000_000:(3000,65),
                                    41_000_000:(3000,65)},horizon=45_000_000)
            (root/'service_decisions.jsonl').write_text(json.dumps(dict(
                rule_version=ServiceDetector.RULE_VERSION,signal='delivery_spacing_shift',
                path=13,decision_t_ns=41_000_000,baseline_ns=1000,deadline_ns=2100,
                tokens=[31_000_000,41_000_000]))+'\n')
            (root/'control_events.csv').write_text('sent_ns,arrival_ns,event,rank,phase,version,wire_bytes\n41000000,42007680,SERVICE_ALARM,13,0,0,96\n')
            (root/'service_alarms.csv').write_text('timestamp_ns,path_id,signal\n42007680,13,delivery_spacing_shift\n')
            (root/'detector_events.csv').write_text('timestamp_ns,path_id,signal,alarm_origin\n42007680,13,delivery_spacing_shift,SERVICE-R\n')
            checked=replay_service(root)
            self.assertTrue(checked['pass_'],checked['errors'])
            self.assertEqual(checked['alarms'],[(13,42_007_680,'delivery_spacing_shift')])
