#!/usr/bin/env python3
"""Opt-in staging and one-shot CTT bench capture; default is local check-only.

Stock 1.3.4 storage write_chunk APPENDS. An uncertain append is never retried.
Stock tx_from_file defaults to ten repeats; zero underflows. Always pass 1 0.
The CLI's 333 ms poll can prolong FSK carrier. CLI completion is not RF proof.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

REMOTE_DIR = '/ext/subghz/stratolink-ctt-20261008-v1'
FIXTURE_DIR = Path(__file__).resolve().parent / 'fixtures/flipper_ctt/base'
HASHES = {
    'ctt_synthetic_valid.sub': 'da933c974330d28f53a80f2e32f4227adc32a8404b817f54f68b43c3a1b0a09f',
    'ctt_synthetic_bad_crc.sub': '4808d061a3965d65e5ad3c734eb3176e45d766c504287a24ee7d725486f94c11',
}
PROMPT = b'>: '
RATE, FREQUENCY, CAPTURE_SECONDS = 1_024_000, 434_000_000, 8
RECEIVE_GAINS_DB = (20.7, 40.2, 49.6)
ABSENT = b'Storage error: file/dir not exist'


class BenchError(RuntimeError):
    pass


class ResponseTimeout(BenchError):
    pass


class Cli:
    def __init__(self, port, clock, sleep):
        self.port, self.clock, self.sleep = port, clock, sleep
        self.trace = []

    def connect(self):
        try:
            self.read_until(PROMPT, 3)
        except ResponseTimeout:
            self.send(b'\r')  # One empty-line prompt request, never a command retry.
            self.read_until(PROMPT, 3)

    def send(self, data):
        self.trace.append({'direction': 'write', 'monotonic': self.clock(),
                           'base64': base64.b64encode(data).decode()})
        if self.port.write(data) != len(data):
            raise BenchError('Short serial write; no retry permitted')
        self.port.flush()

    def read_until(self, marker, timeout):
        started, data = self.clock(), bytearray()
        try:
            while self.clock() - started < timeout:
                data.extend(self.port.read(4096))
                if len(data) > 65536:
                    raise BenchError('Serial response exceeded finite output limit')
                if data.endswith(marker):
                    return bytes(data)
                if marker != PROMPT and data.endswith(PROMPT):
                    raise BenchError('CLI returned without required Ready marker')
            raise ResponseTimeout('Serial response timed out; operation not retried')
        finally:
            self.trace.append({'direction': 'read', 'monotonic': self.clock(),
                               'base64': base64.b64encode(data).decode()})

    def command(self, text, timeout=3):
        if '\r' in text or '\n' in text:
            raise BenchError('Command line injection refused')
        self.send(text.encode('ascii') + b'\r')
        return self.read_until(PROMPT, timeout)

    def append_once(self, path, raw):
        self.send(f'storage write_chunk {path} {len(raw)}\r'.encode())
        self.read_until(b'Ready\r\n', 3)
        self.send(raw)
        check_storage(self.read_until(PROMPT, 3))

    def interrupt(self):
        self.send(b'\x03')
        return self.read_until(PROMPT, 2)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def fixture_files():
    result = {name: (FIXTURE_DIR / name).read_bytes() for name in HASHES}
    validate_fixtures(result)
    return result


def validate_fixtures(fixtures):
    if set(fixtures) != set(HASHES) or any(digest(fixtures[name]) != value for name, value in HASHES.items()):
        raise BenchError('Local fixture set/hash differs from independently reviewed files')


def tx_command(path, repeat):
    if repeat != 1 or type(repeat) is not int or path not in {REMOTE_DIR + '/' + name for name in HASHES}:
        raise BenchError('Only an exact staged fixture path and explicit repeat 1 are permitted')
    return f'subghz tx_from_file {path} 1 0'


def check_storage(response):
    if b'Storage error:' in response or b'Usage:' in response:
        raise BenchError('Storage operation failed; no retry or deletion performed')


def verify_identity(cli):
    raw = cli.command('device_info')
    fields = {}
    for line in raw.decode('utf-8', 'replace').splitlines():
        if ':' in line:
            key, value = line.split(':', 1)
            fields[key.strip()] = value.strip()
    expected = {'firmware_version': '1.3.4', 'firmware_commit': 'ad2a8004',
                'firmware_commit_dirty': 'false', 'firmware_origin_fork': 'Official',
                'hardware_region_provisioned': 'US'}
    if any(fields.get(key) != value for key, value in expected.items()):
        raise BenchError('Expected official clean 1.3.4/ad2a8004 firmware and provisioned US region')
    return expected


def require_absent(cli, path):
    response = cli.command('storage stat ' + path)
    lines = response.replace(b'\r', b'').split(b'\n')
    if ABSENT not in lines or any(line.startswith((b'Directory', b'File, size:')) for line in lines):
        raise BenchError('Remote path is not confirmed absent; refusing mutation')


def read_file(cli, path, expected):
    response = cli.command('storage read ' + path)
    check_storage(response)
    header = re.search(rb'(?:^|\n)Size: ([0-9]+)\r\n', response)
    if not header or int(header[1]) != len(expected):
        raise BenchError('Remote readback size mismatch')
    raw = response[header.end():header.end() + len(expected)]
    if raw != expected or response[header.end() + len(expected):].strip(b'\r\n') != PROMPT:
        raise BenchError('Remote readback bytes/hash or framing mismatch')
    return digest(raw)


def stage(cli, fixtures):
    validate_fixtures(fixtures)
    identity = verify_identity(cli)
    require_absent(cli, REMOTE_DIR)
    check_storage(cli.command('storage mkdir ' + REMOTE_DIR))
    files = {}
    for name, raw in fixtures.items():
        path = REMOTE_DIR + '/' + name
        require_absent(cli, path)
        cli.append_once(path, raw)
        files[name] = {'remote_path': path, 'bytes': len(raw),
                       'sha256': read_file(cli, path, raw), 'readback_verified': True}
    return {'passed': True, 'remote_directory': REMOTE_DIR, 'identity': identity, 'files': files}


def capture_transmit(cli, plan, directory, spawn, clock, sleep):
    command = tx_command(plan['remote_path'], plan['repeat'])
    gain_db = plan.get('gain_db', 20.7)
    if gain_db not in RECEIVE_GAINS_DB:
        raise BenchError('Receive gain must be 20.7, 40.2, or 49.6 dB')
    name = plan['remote_path'].rsplit('/', 1)[-1]
    if plan['expected_sha256'] != HASHES[name] or plan['seconds'] != CAPTURE_SECONDS:
        raise BenchError('Pinned fixture hash or finite capture duration mismatch')
    identity = verify_identity(cli)
    read_file(cli, plan['remote_path'], fixture_files()[name])
    iq_path, log_path = directory / 'capture.u8', directory / 'rtl_sdr.log'
    if iq_path.exists() or iq_path.is_symlink():
        raise BenchError('Capture path already exists')
    arguments = [plan['rtl_sdr'], '-d', plan['rtl_device'], '-f', str(FREQUENCY),
                 '-s', str(RATE), '-g', str(gain_db), '-n', str(RATE * CAPTURE_SECONDS), str(iq_path)]
    process, attempted, last_cli, result = None, False, None, {}
    with log_path.open('xb') as log:
        try:
            process = spawn(arguments, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
            deadline = clock() + 5
            while not iq_path.exists() or iq_path.stat().st_size < 32768:
                if process.poll() is not None or clock() >= deadline:
                    raise BenchError('RTL capture did not establish sample flow; no transmission')
                sleep(0.05)
            flow_size, flow_time = iq_path.stat().st_size, clock()
            sleep(1)
            if process.poll() is not None or iq_path.stat().st_size <= flow_size:
                raise BenchError('RTL sample flow stopped during settling; no transmission')
            settle = clock() - flow_time
            attempted = True
            try:
                response = cli.command(command, timeout=3)
                if b'Listening at ' not in response or any(word in response.lower() for word in
                        (b'restricted', b'error', b'usage:', b'unknown', b'failed')):
                    raise BenchError('TX CLI did not report a clean completed operation')
            except BaseException:
                try:
                    cli.interrupt()
                except Exception:
                    pass  # Full partial response retained; RF termination remains unverified.
                raise
            finally:
                last_cli = clock()
            try:
                status = process.wait(timeout=CAPTURE_SECONDS + 5)
            except subprocess.TimeoutExpired as error:
                raise BenchError('Finite RTL capture subprocess timed out') from error
            if status != 0 or iq_path.stat().st_size != RATE * CAPTURE_SECONDS * 2:
                raise BenchError('Finite RTL capture failed or has unexpected sample count')
            result = {'passed': True, 'identity': identity, 'remote_path': plan['remote_path'],
                      'fixture_sha256': HASHES[name], 'tx_command': command, 'transmit_attempts': 1,
                      'rtl_command': arguments, 'sample_rate': RATE, 'center_hz': FREQUENCY, 'gain_db': gain_db,
                      'complex_samples': RATE * CAPTURE_SECONDS, 'iq_format': 'interleaved unsigned-8 I,Q',
                      'iq_path': str(iq_path), 'iq_sha256': digest(iq_path.read_bytes()),
                      'settle_seconds_after_flow': settle, 'rf_termination_verified': False,
                      'requires_separate_iq_analysis': True}
            return result
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        pass
            if attempted:
                last_cli = clock() if last_cli is None else last_cli
                sleep(max(0, 10 - (clock() - last_cli)))
                result['quiet_seconds_after_cli'] = clock() - last_cli


def make_plan(args):
    fixture_files()
    if args.repeat != 1:
        raise BenchError('Repeat must be exactly 1')
    mode = 'stage' if args.stage else 'capture-transmit' if args.capture_transmit else 'check-only'
    if args.execute_hardware and (mode == 'check-only' or args.output_dir is None):
        raise BenchError('Hardware execution requires an explicit mode and new output directory')
    if args.execute_hardware and not args.serial_port:
        raise BenchError('Hardware execution requires an explicit --serial-port')
    plan = {'mode': mode, 'hardware_execution': args.execute_hardware, 'remote_directory': REMOTE_DIR,
            'fixture_hashes': HASHES, 'repeat': 1, 'seconds': CAPTURE_SECONDS,
            'serial_port': args.serial_port,
            'rtl_sdr': args.rtl_sdr, 'rtl_device': args.rtl_device, 'gain_db': args.gain_db}
    if mode == 'capture-transmit':
        tx_command(args.remote_path, args.repeat)
        name = args.remote_path.rsplit('/', 1)[-1]
        if args.expected_sha256 != HASHES[name] or not args.stage_manifest:
            raise BenchError('Capture requires exact fixture hash and a successful stage manifest')
        document = json.loads(Path(args.stage_manifest).read_text())
        staged = document.get('stage', {})
        file = staged.get('files', {}).get(name, {})
        if (document.get('schema') != 'stratolink.flipper_ctt_bench.v1' or document.get('mode') != 'stage'
                or not document.get('passed') or not staged.get('passed')
                or staged.get('remote_directory') != REMOTE_DIR
                or file.get('remote_path') != args.remote_path or file.get('sha256') != HASHES[name]
                or file.get('readback_verified') is not True):
            raise BenchError('Stage manifest does not attest the selected exact fixture')
        plan.update(remote_path=args.remote_path, expected_sha256=args.expected_sha256,
                    stage_manifest_sha256=digest(Path(args.stage_manifest).read_bytes()))
    return plan


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    modes = p.add_mutually_exclusive_group()
    modes.add_argument('--stage', action='store_true')
    modes.add_argument('--capture-transmit', action='store_true')
    p.add_argument('--execute-hardware', action='store_true')
    p.add_argument('--stage-manifest')
    p.add_argument('--remote-path')
    p.add_argument('--expected-sha256')
    p.add_argument('--repeat', type=int, default=1)
    p.add_argument('--output-dir', type=Path)
    p.add_argument('--serial-port', help='Explicit Flipper serial device; required with --execute-hardware')
    p.add_argument('--rtl-sdr', default='rtl_sdr')
    p.add_argument('--rtl-device', default='0')
    p.add_argument('--gain-db', type=float, choices=RECEIVE_GAINS_DB, default=20.7,
                   help='Fixed RTL-SDR receive gain only; does not change Flipper TX power')
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    plan = make_plan(args)
    if not plan['hardware_execution']:
        print(json.dumps(plan, indent=2))
        return 0
    directory = args.output_dir.resolve()
    directory.mkdir(exist_ok=False)
    report = {'schema': 'stratolink.flipper_ctt_bench.v1', 'mode': plan['mode'], 'passed': False,
              'started_utc': datetime.now(timezone.utc).isoformat(), 'plan': plan,
              'rf_termination_verified': False, 'synthetic_bench_only': True}
    port, cli = None, None
    try:
        import serial
        port = serial.Serial()
        port.port, port.baudrate, port.timeout, port.write_timeout = args.serial_port, 230400, 0.1, 1
        port.dtr, port.rts = True, False
        port.open()
        cli = Cli(port, time.monotonic, time.sleep)
        cli.connect()
        key = 'stage' if plan['mode'] == 'stage' else 'capture'
        report[key] = (stage(cli, fixture_files()) if key == 'stage' else
                       capture_transmit(cli, plan, directory, subprocess.Popen, time.monotonic, time.sleep))
        report['passed'] = True
    except (Exception, KeyboardInterrupt) as error:
        report['error_type'] = type(error).__name__
        report['error'] = str(error)
        report['warning'] = 'No automatic retries; remote partial staging may remain. RF termination is unverified.'
    finally:
        if port is not None:
            port.close()
        report['serial_trace'] = cli.trace if cli is not None else []
        report['finished_utc'] = datetime.now(timezone.utc).isoformat()
        with (directory / 'report.json').open('x') as output:
            json.dump(report, output, indent=2)
            output.write('\n')
    print(json.dumps({'report': str(directory / 'report.json'), 'passed': report['passed'],
                      'rf_termination_verified': False}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
