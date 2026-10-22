import copy
import json
from pathlib import Path
import tempfile
import unittest
from dag_tools import convert_optcc, ring, validate, verify_trace


class GraphGates(unittest.TestCase):
    def setUp(self):
        self.graph = ring(3, 3000)

    def test_ring_bytes_and_dependencies(self):
        self.assertEqual(len(self.graph['flows']), 12)
        self.assertEqual(sum(f['bytes'] for f in self.graph['flows']), 12000)
        self.assertEqual(self.graph['dependency_events'], {'send': 9, 'recv': 9})

    def test_public_golden_graph(self):
        sample = Path(__file__).parent.parent / 'optcc_checks/single_L2/dag.json'
        graph = convert_optcc(json.loads(sample.read_text()), 1048576)
        self.assertEqual(len(graph['flows']), 132)
        self.assertEqual(sum(f['control'] for f in graph['flows']), 40)
        self.assertEqual(graph['dependency_events'], {'send': 127, 'recv': 128})
        self.assertTrue(all(f['rounding_error'] == '0' for f in graph['flows']))
        self.assertEqual([f['id'] for f in graph['flows'] if not f['deps']], [1,4,7,13])

    def test_reject_cycle_missing_parent_and_remote_dependency(self):
        for mutation in ('cycle', 'missing', 'remote', 'duplicate', 'zero'):
            with self.subTest(mutation=mutation):
                flows = copy.deepcopy(self.graph['flows'])
                if mutation == 'cycle':
                    flows[0]['deps'] = [4]
                elif mutation == 'missing':
                    flows[0]['deps'] = [999]
                elif mutation == 'remote':
                    flows[2]['deps'] = [1]
                elif mutation == 'duplicate':
                    flows[3]['deps'] += [1]
                else:
                    flows[0]['bytes'] = 0
                with self.assertRaises(ValueError):
                    validate(flows, 3)

    def test_trace_rejects_early_endpoint_release(self):
        graph = {'flows': [dict(id=1, src=0, dst=1, bytes=100, deps=[]),
                           dict(id=2, src=1, dst=2, bytes=200, deps=[1])]}
        entries = [dict(id=1,event='start',ns=0), dict(id=1,event='send',ns=10),
                   dict(id=1,event='recv',ns=30), dict(id=2,event='start',ns=20),
                   dict(id=2,event='send',ns=40), dict(id=2,event='recv',ns=60)]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'trace.jsonl'
            path.write_text('\n'.join(json.dumps(x) for x in entries))
            with self.assertRaises(ValueError):
                verify_trace(graph, path)
            entries[3]['ns'] = 30
            path.write_text('\n'.join(json.dumps(x) for x in entries))
            self.assertEqual(verify_trace(graph,path)['status'], 'PASS')


if __name__ == '__main__':
    unittest.main()
