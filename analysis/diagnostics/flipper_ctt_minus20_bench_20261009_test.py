"""Offline real-orchestration checks over existing serial/process boundary fakes."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import flipper_ctt_bench_20261009 as old
from flipper_ctt_bench_20261009_test import Clock, Port, Capture

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / 'flipper_ctt_minus20_bench_20261009.py'
NAME = 'ctt_synthetic_valid_minus20.sub'
REMOTE = '/ext/subghz/stratolink-ctt-minus20-20261009-v1/' + NAME
OLD_HASH = 'da933c974330d28f53a80f2e32f4227adc32a8404b817f54f68b43c3a1b0a09f'
OLD_HELPER_HASH = '5e583bda05929a7ba380f725cc2e2b1371f2fd32a8251cfce1743f40098e7710'


class Minus20Tests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.is_file(), 'Missing isolated minus20 fixture adapter')
        spec = importlib.util.spec_from_file_location('minus20_subject', SCRIPT)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.bench = self.module.BENCH

    def cli(self):
        clock = Clock()
        port = Port(clock)
        cli = self.bench.Cli(port, clock.now, clock.sleep)
        cli.connect()
        return cli, port, clock

    def plan(self, **changes):
        return {'remote_path': REMOTE, 'expected_sha256': self.bench.HASHES[NAME],
                'repeat': 1, 'seconds': 8, 'rtl_sdr': 'rtl_sdr', 'rtl_device': '0',
                'gain_db': 20.7, **changes}

    def prepared(self):
        cli, port, clock = self.cli()
        port.directories.add(self.bench.REMOTE_DIR)
        port.files[REMOTE] = self.bench.fixture_files()[NAME]
        return cli, port, clock

    def test_fixture_consumes_exact_old_waveform_with_only_pa_byte_changed(self):
        source = old.fixture_files()['ctt_synthetic_valid.sub']
        files = self.bench.fixture_files()
        self.assertEqual(set(files), {NAME})
        candidate = files[NAME]
        def preset(raw):
            line = next(line for line in raw.splitlines() if line.startswith(b'Custom_preset_data: '))
            return line, bytes.fromhex(line.split(b': ', 1)[1].decode())
        old_line, old_bytes = preset(source)
        new_line, new_bytes = preset(candidate)
        self.assertEqual(len(new_bytes), 46)
        self.assertEqual([(i, a, b) for i, (a, b) in enumerate(zip(old_bytes, new_bytes)) if a != b],
                         [(38, 0x12, 0x0e)])
        self.assertEqual(candidate.replace(new_line, old_line), source)
        runs = [int(value) for value in candidate.split(b'RAW_Data: ', 1)[1].split()]
        bits = ''.join(('1' if value > 0 else '0') * (abs(value) // 40) for value in runs)
        self.assertTrue(all(value and abs(value) % 40 == 0 for value in runs))
        self.assertEqual(len(bits), 80)
        self.assertEqual(sum(map(abs, runs)), 3200)
        self.assertEqual(int(bits, 2).to_bytes(10, 'big'), bytes.fromhex('AAAAAAD39178554C3358'))

    def test_old_helper_and_its_allowlist_are_not_relaxed(self):
        self.assertEqual(hashlib.sha256((HERE / 'flipper_ctt_bench_20261009.py').read_bytes()).hexdigest(), OLD_HELPER_HASH)
        with self.assertRaises(old.BenchError): old.tx_command(REMOTE, 1)
        self.assertEqual(old.HASHES['ctt_synthetic_valid.sub'], OLD_HASH)
        with self.assertRaises(self.bench.BenchError):
            self.bench.tx_command(old.REMOTE_DIR + '/ctt_synthetic_valid.sub', 1)

    def test_helper_drift_refused_before_private_import(self):
        read_bytes = Path.read_bytes
        def tampered(path):
            data = read_bytes(path)
            return data + b'\n' if path == HERE / 'flipper_ctt_bench_20261009.py' else data
        with patch.object(Path, 'read_bytes', tampered):
            spec = importlib.util.spec_from_file_location('minus20_tampered', SCRIPT)
            module = importlib.util.module_from_spec(spec)
            with self.assertRaises(RuntimeError): spec.loader.exec_module(module)

    def test_check_only_creates_nothing_and_exposes_bound_provenance(self):
        def forbidden(): self.fail('Check-only opened serial')
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'absent'
            with patch.dict(sys.modules, {'serial': types.SimpleNamespace(Serial=forbidden)}), \
                 contextlib.redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(self.module.main(['--stage', '--output-dir', str(output)]), 0)
            plan = json.loads(stdout.getvalue())
            self.assertFalse(plan['hardware_execution'])
            self.assertFalse(output.exists())
            proof = plan['minus20_diagnostic']
            self.assertEqual(proof['base_helper_sha256'], OLD_HELPER_HASH)
            self.assertEqual(proof['adapter_sha256'], hashlib.sha256(SCRIPT.read_bytes()).hexdigest())
            self.assertEqual(proof['preset_delta'], {'byte_index': 38, 'before': 18, 'after': 14})
            self.assertEqual(proof['nominal_tx_dbm'], -20)
            self.assertIs(proof['calibrated_power'], False)
            self.assertEqual(plan['repeat'], 1)
            self.assertEqual(plan['seconds'], 8)

    def test_stage_appends_only_one_new_valid_file_and_verifies_readback(self):
        cli, port, _ = self.cli()
        result = self.bench.stage(cli, self.bench.fixture_files())
        self.assertTrue(result['passed'])
        self.assertEqual(set(port.files), {REMOTE})
        self.assertEqual(port.files[REMOTE], self.bench.fixture_files()[NAME])
        self.assertEqual(sum(value.startswith(b'storage write_chunk ') for value in port.writes), 1)
        self.assertEqual(port.tx_count, 0)

    def test_existing_directory_and_wrong_identity_refuse_before_write(self):
        for mode in ('existing', 'version', 'region'):
            cli, port, _ = self.cli()
            if mode == 'existing': port.directories.add(self.bench.REMOTE_DIR)
            elif mode == 'version': port.version = '1.3.3'
            else: port.region = 'EU'
            with self.subTest(mode=mode), self.assertRaises(self.bench.BenchError):
                self.bench.stage(cli, self.bench.fixture_files())
            self.assertFalse(any(b'mkdir' in row or b'write_chunk' in row for row in port.writes))

    def test_partial_append_failure_has_no_retry(self):
        cli, port, _ = self.cli()
        port.fail_append = True
        with self.assertRaises(self.bench.BenchError): self.bench.stage(cli, self.bench.fixture_files())
        self.assertEqual(sum(value.startswith(b'storage write_chunk ') for value in port.writes), 1)
        self.assertEqual(port.tx_count, 0)

    def test_invalid_path_repeat_fixture_hash_and_duration_refuse_before_io(self):
        for change in ({'repeat': 0}, {'repeat': True}, {'repeat': 2}, {'remote_path': REMOTE + '\rhelp'},
                       {'remote_path': old.REMOTE_DIR + '/ctt_synthetic_valid.sub'},
                       {'expected_sha256': OLD_HASH}, {'seconds': 9}):
            cli, port, clock = self.prepared()
            capture = Capture(clock)
            with tempfile.TemporaryDirectory() as folder, self.subTest(change=change), \
                 self.assertRaises(self.bench.BenchError):
                self.bench.capture_transmit(cli, self.plan(**change), Path(folder), capture, clock.now, clock.sleep)
            self.assertEqual(port.writes, [])
            self.assertIsNone(capture.args)

    def test_one_exact_tx_and_finite_iq_with_unchanged_quiet(self):
        cli, port, clock = self.prepared()
        capture = Capture(clock)
        with tempfile.TemporaryDirectory() as folder:
            result = self.bench.capture_transmit(cli, self.plan(), Path(folder), capture, clock.now, clock.sleep)
            self.assertEqual(capture.args, ['rtl_sdr', '-d', '0', '-f', '434000000', '-s', '1024000',
                                          '-g', '20.7', '-n', '8192000', str(Path(folder) / 'capture.u8')])
        self.assertEqual([value for value in port.writes if value.startswith(b'subghz ')],
                         [f'subghz tx_from_file {REMOTE} 1 0\r'.encode()])
        self.assertEqual(result['transmit_attempts'], 1)
        self.assertAlmostEqual(result['settle_seconds_after_flow'], 1, places=9)
        self.assertGreaterEqual(result['quiet_seconds_after_cli'], 10)
        self.assertFalse(result['rf_termination_verified'])

    def test_timeout_interrupts_once_without_tx_retry_and_no_flow_never_transmits(self):
        for mode in ('timeout', 'no_flow'):
            cli, port, clock = self.prepared()
            port.timeout_tx = mode == 'timeout'
            capture = Capture(clock, flowing=mode != 'no_flow')
            start = clock.now()
            with tempfile.TemporaryDirectory() as folder, self.subTest(mode=mode), \
                 self.assertRaises(self.bench.BenchError):
                self.bench.capture_transmit(cli, self.plan(), Path(folder), capture, clock.now, clock.sleep)
            self.assertEqual(port.tx_count, 1 if mode == 'timeout' else 0)
            self.assertEqual(port.writes.count(b'\x03'), 1 if mode == 'timeout' else 0)
            self.assertTrue(capture.finished or capture.terminated or capture.killed)
            if mode == 'timeout': self.assertGreaterEqual(clock.now() - start, 14)

    def test_old_stage_manifest_cannot_authorize_new_fixture(self):
        cli, _, _ = self.cli()
        staged = self.bench.stage(cli, self.bench.fixture_files())
        with tempfile.TemporaryDirectory() as folder:
            manifest = Path(folder) / 'stage.json'
            good = {'schema': 'stratolink.flipper_ctt_bench.v1', 'mode': 'stage', 'passed': True, 'stage': staged}
            manifest.write_text(json.dumps(good))
            args = self.bench.parser().parse_args(['--capture-transmit', '--remote-path', REMOTE,
                    '--expected-sha256', self.bench.HASHES[NAME], '--stage-manifest', str(manifest)])
            self.assertFalse(self.bench.make_plan(args)['hardware_execution'])
            good['stage']['remote_directory'] = old.REMOTE_DIR
            manifest.write_text(json.dumps(good))
            with self.assertRaises(self.bench.BenchError): self.bench.make_plan(args)

    def test_fixture_tampering_is_rejected(self):
        files = self.bench.fixture_files()
        for bad in ({NAME: files[NAME].replace(b'434000000', b'916000000')},
                    {NAME: files[NAME].replace(b'RAW_Data: 40 ', b'RAW_Data: 80 ', 1)},
                    {'ctt_synthetic_valid.sub': files[NAME]}):
            with self.assertRaises(self.bench.BenchError): self.bench.validate_fixtures(bad)

    def test_exact_delta_check_still_refuses_changed_waveform_with_matching_hash(self):
        raw = self.bench.fixture_files()[NAME].replace(b'RAW_Data: 40 ', b'RAW_Data: 80 ', 1)
        with patch.object(self.bench, 'HASHES', {NAME: hashlib.sha256(raw).hexdigest()}):
            with self.assertRaisesRegex(self.bench.BenchError, 'Only PATABLE'):
                self.bench.validate_fixtures({NAME: raw})


if __name__ == '__main__':
    unittest.main()
