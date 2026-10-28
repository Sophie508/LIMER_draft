"""A binary hash alone must not hide changed transport libraries or path escapes."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
from limerlab.paths import sha
from limerlab.runner import resolve_build


def fixture(root):
    (root / 'lib').mkdir()
    (root / 'simulator').write_bytes(b'not executed by these metadata checks')
    (root / 'lib/transport.so').write_bytes(b'original transport')
    record = dict(schema='limer-build-v1', binary_relative='simulator', libraries_relative='lib',
                  binary_sha256=sha(root / 'simulator'), library_hashes={'transport.so': sha(root / 'lib/transport.so')})
    (root / 'build.json').write_text(json.dumps(record))
    return record


class BuildIntegrityTests(unittest.TestCase):
    def test_valid_build_record(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); fixture(root)
            _, binary, libraries = resolve_build(root)
            self.assertEqual(binary, (root / 'simulator').resolve())
            self.assertEqual(libraries, (root / 'lib').resolve())

    def test_transport_change_rejected_even_with_unchanged_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); fixture(root)
            (root / 'lib/transport.so').write_bytes(b'different transport')
            with self.assertRaises(ValueError): resolve_build(root)

    def test_descriptor_cannot_redirect_binary_outside_build(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); record = fixture(root)
            record['binary_relative'] = '../outside'
            (root / 'build.json').write_text(json.dumps(record))
            with self.assertRaises(ValueError): resolve_build(root)


if __name__ == '__main__':
    unittest.main()
