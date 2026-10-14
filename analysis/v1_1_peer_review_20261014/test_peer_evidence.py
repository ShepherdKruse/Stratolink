"""Meaningful integrity/portability failure tests; no real CAD/package mutation."""
import hashlib, json, shutil, tempfile, unittest
from pathlib import Path
import verify_peer_evidence as v
from freeze_peer_evidence import freeze

class PeerEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'checkout'
        self.root.mkdir()
        self.pcb = 'hardware/pcb/stratolink.kicad_pcb'
        self.review = 'analysis/v1_1_peer_review_20261014/final-test-review.json'
        self.spec = 'analysis/v1_1_peer_review_20261014/test-inputs.json'
        self.pkg = 'hardware/gerbers/v1.1-pilot/manifest.json'
        self.write(self.pcb, 'synthetic CAD fixture\n')
        self.write(self.review, json.dumps({'final_pcb_sha256': v.sha(self.root / self.pcb)}))
        for name in ['verify_peer_evidence.py', 'freeze_peer_evidence.py']:
            source = Path(__file__).with_name(name)
            self.write('analysis/v1_1_peer_review_20261014/' + name, source.read_text())
        self.write(self.spec, json.dumps({'review_evidence': [self.review], 'bindings': [{'evidence': self.review, 'pointer': '/final_pcb_sha256', 'source': self.pcb}], 'scope': 'Synthetic integrity test only'}))
        self.write(self.pkg, json.dumps({'source_files': {'stratolink.kicad_pcb': v.sha(self.root / self.pcb)}}))
        freeze(self.root, Path(self.pkg), Path(self.spec), Path(v.DEFAULT_MANIFEST))
        self.manifest = self.root / v.DEFAULT_MANIFEST
        self.original = self.manifest.read_text()
    def tearDown(self):
        self.temp.cleanup()
    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    def mutate(self, f):
        m = json.loads(self.original)
        f(m)
        self.manifest.write_text(json.dumps(m))
    def test_positive_and_relocated_checkout(self):
        self.assertEqual(v.verify(self.root)['bindings'], 1)
        other = Path(self.temp.name) / 'different absolute checkout'
        shutil.copytree(self.root, other)
        self.assertEqual(v.verify(other)['reviewed_sources'], 1)
    def test_current_source_changed(self):
        self.write(self.pcb, 'changed')
        with self.assertRaises(ValueError): v.verify(self.root)
    def test_evidence_changed_and_missing(self):
        self.write(self.review, 'changed')
        with self.assertRaises(ValueError): v.verify(self.root)
        (self.root / self.review).unlink()
        with self.assertRaises(ValueError): v.verify(self.root)
    def test_rehashed_stale_evidence_binding(self):
        self.write(self.review, json.dumps({'final_pcb_sha256': '0' * 64}))
        self.mutate(lambda m: m['review_evidence'].__setitem__(self.review, v.sha(self.root / self.review)))
        with self.assertRaisesRegex(ValueError, 'another CAD version'): v.verify(self.root)
    def test_duplicate_json_at_any_depth(self):
        for text in ['{"schema":1,"schema":2}', '{"x":{"y":1,"y":2}}']:
            self.manifest.write_text(text)
            with self.assertRaisesRegex(ValueError, 'Duplicate'): v.verify(self.root)
    def test_unsafe_paths_and_invalid_hash(self):
        for path in ['../outside', '/absolute', 'hardware/../outside', './same', 'a//b', 'C:/file', 'a\\b']:
            self.mutate(lambda m: m['review_evidence'].__setitem__(path, '0' * 64))
            with self.assertRaises(ValueError): v.verify(self.root)
        self.mutate(lambda m: m['reviewed_sources'].__setitem__(self.pcb, 'ABC'))
        with self.assertRaises(ValueError): v.verify(self.root)
    def test_symlink_escape(self):
        outside = Path(self.temp.name) / 'outside.txt'; outside.write_text('outside')
        (self.root / 'escape').symlink_to(outside)
        self.mutate(lambda m: m['review_evidence'].__setitem__('escape', v.sha(outside)))
        with self.assertRaisesRegex(ValueError, 'escapes'): v.verify(self.root)
    def test_no_or_duplicate_binding(self):
        for bindings in [[], [json.loads(self.original)['bindings'][0]] * 2]:
            self.mutate(lambda m: m.__setitem__('bindings', bindings))
            with self.assertRaises(ValueError): v.verify(self.root)
    def test_overwrite_is_rejected_without_mutation(self):
        with self.assertRaisesRegex(ValueError, 'overwrite'):
            freeze(self.root, Path(self.pkg), Path(self.spec), Path(v.DEFAULT_MANIFEST))
        self.assertEqual(self.manifest.read_text(), self.original)
    def test_failed_freeze_leaves_no_manifest(self):
        self.manifest.unlink()
        self.write(self.pcb, 'stale package source')
        with self.assertRaises(ValueError):
            freeze(self.root, Path(self.pkg), Path(self.spec), Path(v.DEFAULT_MANIFEST))
        self.assertFalse(self.manifest.exists())
        self.assertEqual(list(self.manifest.parent.glob('.peer-evidence-*')), [])

if __name__ == '__main__':
    unittest.main()
