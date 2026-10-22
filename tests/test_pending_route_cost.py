import unittest

from limer_v0.pending_route_cost import pending_route_cost


class PendingCostTests(unittest.TestCase):
    def test_helpful_alternative(self):
        result=pending_route_cost(1_000_000,1_000_000,0,0,.02,.1,0)
        self.assertTrue(result['switch'])
        self.assertEqual(result['stay_ns'],50_000_000)
        self.assertEqual(result['switch_ns'],20_010_000)

    def test_slow_alternative(self):
        self.assertFalse(pending_route_cost(1_000_000,0,0,0,.1,.02,0)['switch'])

    def test_launched_work_cannot_be_rescued(self):
        result=pending_route_cost(100_000,0,10_000_000,0,.02,.1,0)
        self.assertEqual(result['switch_ns'],500_010_000)

    def test_no_pending_work(self):
        self.assertFalse(pending_route_cost(0,0,1_000_000,0,.02,.1,0)['switch'])

    def test_unknown_and_stale_alternative(self):
        for rate,age in ((None,0),(.1,None),(.1,20_000_001),(0,0)):
            self.assertEqual(pending_route_cost(1,0,0,0,.02,rate,age)['reason'],
                             'unknown_or_stale_service')

    def test_tie_stays(self):
        self.assertFalse(pending_route_cost(1000,0,0,0,.05,.1,0)['switch'])


if __name__=='__main__':
    unittest.main()
