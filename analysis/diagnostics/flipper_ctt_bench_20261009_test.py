"""No hardware: exercise real orchestration over protocol/process boundary fakes."""
import hashlib
import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch

import flipper_ctt_bench_20261009 as bench

VALID = 'ctt_synthetic_valid.sub'
BAD = 'ctt_synthetic_bad_crc.sub'
HASH = 'da933c974330d28f53a80f2e32f4227adc32a8404b817f54f68b43c3a1b0a09f'
REMOTE = bench.REMOTE_DIR + '/' + VALID


class Clock:
    def __init__(self):
        self.value, self.callbacks = 0.0, []

    def now(self):
        return self.value

    def sleep(self, duration):
        self.value += duration
        for callback in self.callbacks:
            callback()


class Port:
    """Small model of observed stock CLI echo, prompt, append, read and TX."""
    def __init__(self, clock):
        self.clock = clock
        self.rx = bytearray(b'Official Flipper CLI\r\n>: ')
        self.writes, self.files, self.directories = [], {}, set()
        self.pending = None
        self.timeout_tx = self.fail_append = self.corrupt_read = False
        self.version = '1.3.4'
        self.region = 'US'
        self.tx_count = 0

    def write(self, data):
        self.writes.append(data)
        if data == b'\x03':
            self.rx.extend(b'Interrupted\r\n>: ')
            return 1
        if self.pending:
            path, count = self.pending
            assert len(data) == count
            self.files[path] = self.files.get(path, b'') + data
            self.pending = None
            if not self.fail_append:
                self.rx.extend(b'\r\n>: ')
            return len(data)
        command = data.decode().rstrip('\r\n')
        self.rx.extend(command.encode() + b'\r\n')
        parts = command.split()
        if not command:
            pass
        elif command == 'device_info':
            self.rx.extend((f'firmware_version : {self.version}\r\nfirmware_commit : ad2a8004\r\n'
                            'firmware_commit_dirty : false\r\nfirmware_origin_fork : Official\r\n'
                            f'hardware_region_provisioned : {self.region}\r\n').encode())
        elif parts[:2] == ['storage', 'stat']:
            path = parts[2]
            if path in self.directories:
                self.rx.extend(b'Directory\r\n')
            elif path in self.files:
                self.rx.extend(f'File, size: {len(self.files[path])}b\r\n'.encode())
            else:
                self.rx.extend(b'Storage error: file/dir not exist\r\n')
        elif parts[:2] == ['storage', 'mkdir']:
            self.directories.add(parts[2])
        elif parts[:2] == ['storage', 'write_chunk']:
            self.pending = parts[2], int(parts[3])
            self.rx.extend(b'Ready\r\n')
            return len(data)
        elif parts[:2] == ['storage', 'read']:
            raw = self.files[parts[2]]
            if self.corrupt_read:
                raw = raw[:-1] + b'!'
            self.rx.extend(f'Size: {len(raw)}\r\n'.encode() + raw + b'\r\n')
        elif parts[:2] == ['subghz', 'tx_from_file']:
            self.tx_count += 1
            self.rx.extend(b'Listening at synthetic fixture\r\n.\r\n')
            if self.timeout_tx:
                return len(data)
        else:
            raise AssertionError('unexpected command: ' + command)
        self.rx.extend(b'>: ')
        return len(data)

    def flush(self):
        pass

    def read(self, count):
        self.clock.sleep(0.02)
        # Fragment responses deliberately, including Ready and the prompt.
        count = min(count, 13, len(self.rx))
        result = bytes(self.rx[:count])
        del self.rx[:count]
        return result


class Capture:
    def __init__(self, clock, flowing=True):
        self.clock, self.flowing = clock, flowing
        self.args = None
        self.finished = self.terminated = self.killed = False
        self.start = clock.now()
        self.returncode = None
        clock.callbacks.append(self.advance)

    def __call__(self, args, **kwargs):
        self.args = args
        self.path = Path(args[-1])
        self.path.touch(exist_ok=False)
        return self

    def advance(self):
        if self.args and self.flowing and not self.finished:
            with self.path.open('r+b') as handle:
                handle.truncate(min(16_384_000, int((self.clock.now() - self.start) * 2_048_000)))

    def poll(self):
        return self.returncode

    def wait(self, timeout):
        if not self.flowing:
            raise subprocess.TimeoutExpired('rtl_sdr', timeout)
        self.clock.sleep(8)
        self.returncode, self.finished = 0, True
        return 0

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def kill(self):
        self.killed = True
        self.returncode = -9


class BenchTest(unittest.TestCase):
    def cli(self):
        clock = Clock()
        port = Port(clock)
        cli = bench.Cli(port, clock.now, clock.sleep)
        cli.connect()
        return cli, port, clock

    def prepared(self):
        cli, port, clock = self.cli()
        fixtures = bench.fixture_files()
        port.directories.add(bench.REMOTE_DIR)
        port.files.update({bench.REMOTE_DIR + '/' + name: raw for name, raw in fixtures.items()})
        plan = {'remote_path': REMOTE, 'expected_sha256': HASH, 'repeat': 1,
                'seconds': 8, 'rtl_sdr': 'rtl_sdr', 'rtl_device': '0'}
        return cli, port, clock, plan

    def test_stage_writes_each_new_file_once_and_verifies_exact_readback(self):
        cli, port, _ = self.cli()
        fixtures = bench.fixture_files()
        result = bench.stage(cli, fixtures)
        self.assertTrue(result.get('passed'))
        self.assertEqual(set(port.files), {bench.REMOTE_DIR + '/' + VALID, bench.REMOTE_DIR + '/' + BAD})
        self.assertEqual(port.files[REMOTE], fixtures[VALID])
        commands = [value for value in port.writes if value.startswith(b'storage write_chunk ')]
        self.assertEqual(len(commands), 2)
        self.assertEqual(result['files'][VALID]['sha256'], HASH)

    def test_missing_initial_prompt_uses_only_one_empty_line_fallback(self):
        clock = Clock()
        port = Port(clock)
        port.rx.clear()
        cli = bench.Cli(port, clock.now, clock.sleep)
        failure = None
        try:
            cli.connect()
        except bench.BenchError as error:
            failure = str(error)
        self.assertIsNone(failure, 'missing banner should recover with one empty line')
        self.assertEqual(port.writes, [b'\r'])

    def test_existing_stage_directory_refused_without_any_mutation(self):
        cli, port, _ = self.cli()
        port.directories.add(bench.REMOTE_DIR)
        with self.assertRaises(bench.BenchError):
            bench.stage(cli, bench.fixture_files())
        self.assertFalse(port.files)
        self.assertFalse(any(b'mkdir' in value or b'write_chunk' in value for value in port.writes))

    def test_partial_append_timeout_never_retries_or_deletes(self):
        cli, port, _ = self.cli()
        port.fail_append = True
        with self.assertRaises(bench.BenchError):
            bench.stage(cli, bench.fixture_files())
        self.assertEqual(sum(value.startswith(b'storage write_chunk ') for value in port.writes), 1)
        self.assertEqual(len(port.files), 1)
        self.assertNotIn(b'\x03', port.writes)

    def test_readback_corruption_refused(self):
        cli, port, _ = self.cli()
        port.corrupt_read = True
        with self.assertRaises(bench.BenchError):
            bench.stage(cli, bench.fixture_files())
        self.assertEqual(sum(value.startswith(b'storage write_chunk ') for value in port.writes), 1)

    def test_wrong_firmware_or_region_refused_before_storage_write(self):
        for field, value in [('version', '1.3.3'), ('region', 'EU')]:
            cli, port, _ = self.cli()
            setattr(port, field, value)
            with self.assertRaises(bench.BenchError):
                bench.stage(cli, bench.fixture_files())
            self.assertFalse(port.files or port.directories)

    def test_tx_rejects_other_paths_injection_and_any_repeat_except_explicit_one(self):
        for path, repeat in [(REMOTE, 0), (REMOTE, 2), (REMOTE, None),
                             (REMOTE + '\rhelp', 1), ('/ext/subghz/existing.sub', 1),
                             (bench.REMOTE_DIR + '/../x.sub', 1)]:
            with self.assertRaises(bench.BenchError):
                bench.tx_command(path, repeat)
        self.assertEqual(bench.tx_command(REMOTE, 1), f'subghz tx_from_file {REMOTE} 1 0')

    def test_one_tx_after_sample_flow_capture_finite_and_ten_second_quiet(self):
        cli, port, clock, plan = self.prepared()
        capture = Capture(clock)
        with tempfile.TemporaryDirectory() as temporary:
            result = bench.capture_transmit(cli, plan, Path(temporary), capture, clock.now, clock.sleep)
            self.assertTrue(result.get('passed'))
            self.assertEqual(port.tx_count, 1)
            self.assertIn(str(8_192_000), capture.args)
            self.assertIn('434000000', capture.args)
            self.assertIn('1024000', capture.args)
            self.assertEqual(capture.args[capture.args.index('-g') + 1], '20.7')
            self.assertGreaterEqual(result['quiet_seconds_after_cli'], 10)
            self.assertFalse(result['rf_termination_verified'])
            self.assertGreaterEqual(result['settle_seconds_after_flow'], 1)

    def test_selected_receiver_gain_reaches_rtl_and_report_without_changing_tx(self):
        for gain in (40.2, 49.6):
            cli, port, clock, plan = self.prepared()
            plan['gain_db'] = gain
            capture = Capture(clock)
            with tempfile.TemporaryDirectory() as temporary:
                result = bench.capture_transmit(cli, plan, Path(temporary), capture, clock.now, clock.sleep)
            self.assertEqual(capture.args[capture.args.index('-g') + 1], str(gain))
            self.assertEqual(result.get('gain_db'), gain)
            self.assertEqual(result['tx_command'], f'subghz tx_from_file {REMOTE} 1 0')
            self.assertEqual(result['fixture_sha256'], HASH)
            self.assertEqual(port.tx_count, 1)

    def test_capture_rejects_unapproved_gain_before_any_device_command(self):
        cli, port, clock, plan = self.prepared()
        plan['gain_db'] = 50.0
        capture = Capture(clock)
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(bench.BenchError):
                bench.capture_transmit(cli, plan, Path(temporary), capture, clock.now, clock.sleep)
        self.assertEqual(port.writes, [])
        self.assertIsNone(capture.args)

    def test_absent_sample_flow_prevents_transmission_and_cleans_subprocess(self):
        cli, port, clock, plan = self.prepared()
        capture = Capture(clock, flowing=False)
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(bench.BenchError):
                bench.capture_transmit(cli, plan, Path(temporary), capture, clock.now, clock.sleep)
        self.assertEqual(port.tx_count, 0)
        self.assertTrue(capture.terminated or capture.killed)

    def test_tx_timeout_sends_one_emergency_interrupt_then_quiet_no_retry(self):
        cli, port, clock, plan = self.prepared()
        port.timeout_tx = True
        capture = Capture(clock)
        with tempfile.TemporaryDirectory() as temporary:
            start = clock.now()
            with self.assertRaises(bench.BenchError):
                bench.capture_transmit(cli, plan, Path(temporary), capture, clock.now, clock.sleep)
        self.assertEqual(port.tx_count, 1)
        self.assertEqual(port.writes.count(b'\x03'), 1)
        self.assertGreaterEqual(clock.now() - start, 14)
        self.assertTrue(capture.finished or capture.terminated or capture.killed)

    def test_wrong_remote_hash_prevents_capture_and_tx(self):
        cli, port, clock, plan = self.prepared()
        port.files[REMOTE] = b'wrong contents'
        capture = Capture(clock)
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(bench.BenchError):
                bench.capture_transmit(cli, plan, Path(temporary), capture, clock.now, clock.sleep)
        self.assertIsNone(capture.args)
        self.assertEqual(port.tx_count, 0)

    def test_default_plan_is_check_only_and_unstaged_capture_is_rejected(self):
        plan = bench.make_plan(bench.parser().parse_args([]))
        self.assertFalse(plan.get('hardware_execution', True))
        self.assertEqual(plan.get('gain_db'), 20.7)
        with self.assertRaises(bench.BenchError):
            bench.make_plan(bench.parser().parse_args(['--capture-transmit', '--remote-path', REMOTE,
                                                      '--expected-sha256', HASH]))

    def test_gain_cli_allows_only_reviewed_receiver_settings(self):
        for gain in ('20.7', '40.2', '49.6'):
            try:
                with contextlib.redirect_stderr(io.StringIO()):
                    args = bench.parser().parse_args(['--gain-db', gain])
            except SystemExit:
                self.fail('reviewed receiver gain option was rejected')
            self.assertEqual(bench.make_plan(args).get('gain_db'), float(gain))
        for gain in ('0', '50', 'nan', 'inf'):
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    bench.parser().parse_args(['--gain-db', gain])

    def test_prior_stage_manifest_without_gain_remains_compatible(self):
        cli, _, _ = self.cli()
        staged = bench.stage(cli, bench.fixture_files())
        with tempfile.TemporaryDirectory() as temporary:
            manifest = Path(temporary) / 'prior_stage.json'
            manifest.write_text(json.dumps({'schema': 'stratolink.flipper_ctt_bench.v1',
                                            'mode': 'stage', 'passed': True, 'stage': staged}))
            args = bench.parser().parse_args(['--capture-transmit', '--remote-path', REMOTE,
                    '--expected-sha256', HASH, '--stage-manifest', str(manifest)])
            args.gain_db = 49.6
            plan = bench.make_plan(args)
        self.assertEqual(plan.get('gain_db'), 49.6)
        self.assertEqual(plan['expected_sha256'], HASH)

    def test_main_without_hardware_flag_never_opens_serial_or_creates_output(self):
        def forbidden_serial():
            self.fail('check-only attempted to open serial')
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'must_not_exist'
            with patch.dict('sys.modules', {'serial': types.SimpleNamespace(Serial=forbidden_serial)}):
                with contextlib.redirect_stdout(io.StringIO()) as stdout:
                    status = bench.main(['--stage', '--output-dir', str(output)])
            self.assertEqual(status, 0)
            self.assertFalse(output.exists())
            self.assertFalse(json.loads(stdout.getvalue())['hardware_execution'])

    def test_hardware_execution_requires_explicit_serial_port_before_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'must_not_exist'
            args = bench.parser().parse_args([
                '--stage', '--execute-hardware', '--output-dir', str(output)])
            with patch.object(bench, 'fixture_files', return_value={}):
                with self.assertRaisesRegex(bench.BenchError, '--serial-port'):
                    bench.make_plan(args)
            self.assertFalse(output.exists())

    def test_serial_target_has_no_machine_default_and_is_recorded_in_plan(self):
        self.assertIsNone(bench.parser().parse_args([]).serial_port)
        args = bench.parser().parse_args([
            '--stage', '--execute-hardware', '--output-dir', 'new-capture',
            '--serial-port', '/dev/test-flipper'])
        with patch.object(bench, 'fixture_files', return_value={}):
            self.assertEqual(bench.make_plan(args)['serial_port'], '/dev/test-flipper')

    def test_tampered_stage_manifest_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            manifest = Path(temporary) / 'stage.json'
            manifest.write_text(json.dumps({'schema': 'stratolink.flipper_ctt_bench.v1',
                'mode': 'stage', 'passed': True, 'stage': {'passed': True,
                'remote_directory': bench.REMOTE_DIR, 'files': {VALID: {
                'remote_path': REMOTE, 'sha256': '0' * 64, 'readback_verified': True}}}}))
            with self.assertRaises(bench.BenchError):
                bench.make_plan(bench.parser().parse_args(['--capture-transmit', '--remote-path', REMOTE,
                    '--expected-sha256', HASH, '--stage-manifest', str(manifest)]))


if __name__ == '__main__':
    unittest.main()
