"""Retain the native pilot's phase/report race without weakening explicit release."""
import unittest
from limerlab.audit import audit_explicit_lease_drains


def controls():
    # Exact identities and timestamps from retained pilot-v1 blackhole candidate.
    entries = [
        ('LEND_TX',1,2,50981,41_650_000,42_657_680,96),
        ('LEND_RX',5,2,50981,41_650_000,42_665_360,96),
        ('LEND_ACTIVE',0,2,50981,42_665_360,42_665_360,0),
        ('LEND_TX',12,2,50982,41_650_000,42_673_040,96),
        ('LEND_RX',2,2,50982,41_650_000,42_680_720,96),
        ('LEND_ACTIVE',15,2,50982,42_680_720,42_680_720,0),
        ('HEALTH_REPORT',0,2,76618,63_160_070,64_167_750,96),
        ('HEALTH_REPORT',15,2,76623,63_262_114,64_269_794,96),
        ('RELEASE_TX',1,2,50981,63_500_000,64_507_680,96),
        ('RELEASE_RX',5,2,50981,63_500_000,64_515_360,96),
        ('RESET_TO_AB',0,3,76627,63_637_881,63_637_881,0),
    ]
    return [dict(zip(('event','rank','phase','version','sent_ns','arrival_ns','wire_bytes'),r)) for r in entries]


def reservations():
    return {76618:dict(relay=1,probe=1,phase=2,src=0,helper_src=1,helper_dst=5,timestamp_ns=63_100_000),
            76623:dict(relay=1,probe=1,phase=2,src=15,helper_src=12,helper_dst=2,timestamp_ns=63_200_000)}


def explicit(src,lease,at):
    return dict(event='LEND_RELEASED',rank=src,phase=2,version=lease,sent_ns=at,arrival_ns=at,wire_bytes=0)


class HelperPhaseDrainAuditTests(unittest.TestCase):
    def test_real_phase_boundary_does_not_release_pending_health_reservations(self):
        actual_release={76618:64_167_750,76623:64_269_794}
        self.assertEqual(audit_explicit_lease_drains(controls(),reservations(),actual_release),[])

    def test_explicit_release_of_live_probe_still_fails(self):
        actual_release={76618:64_167_750,76623:64_269_794}
        for src,lease in ((0,50981),(15,50982)):
            with self.subTest(source=src):
                result=audit_explicit_lease_drains(controls()+[explicit(src,lease,63_600_000)],
                                                  reservations(),actual_release)
                self.assertEqual(result,['lease release erased live relay ownership'])

    def test_explicit_release_without_physical_release_still_fails(self):
        result=audit_explicit_lease_drains(controls()+[explicit(0,50981,63_600_000)],reservations(),{})
        self.assertEqual(result,['lease release erased live relay ownership'])

    def test_live_business_reservation_is_not_exempted(self):
        owned=reservations();owned[76618]['probe']=0
        result=audit_explicit_lease_drains(controls()+[explicit(0,50981,63_600_000)],owned,
                                          {76618:64_167_750,76623:64_269_794})
        self.assertEqual(result,['lease release erased live relay ownership'])

    def test_explicit_release_after_its_physical_drain_passes(self):
        result=audit_explicit_lease_drains(controls()+[explicit(0,50981,63_600_000)],reservations(),
                                          {76618:63_500_000,76623:64_269_794})
        self.assertEqual(result,[])

if __name__=='__main__':unittest.main()
