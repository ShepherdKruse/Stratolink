#!/usr/bin/env python3
"""Conditional synthetic 434 MHz power-step diagnostic; check-only by default.

An operator must explicitly approve staging or transmission for this bench test.
Nominal -20 dBm is not calibrated radiated power, compliance or a receiver fix.
The frozen -30 dBm helper and fixtures are never modified by this adapter.
"""
import hashlib
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE_PATH = HERE / 'flipper_ctt_bench_20261009.py'
BASE_SHA256 = '5e583bda05929a7ba380f725cc2e2b1371f2fd32a8251cfce1743f40098e7710'
ORIGINAL = HERE / 'fixtures/flipper_ctt/base/ctt_synthetic_valid.sub'
ORIGINAL_SHA256 = 'da933c974330d28f53a80f2e32f4227adc32a8404b817f54f68b43c3a1b0a09f'
FIXTURE_NAME = 'ctt_synthetic_valid_minus20.sub'
FIXTURE_SHA256 = '5034d151ff0c788767e6276775b892bd2fd325c79061e4a1716d3b1894fc9495'

if hashlib.sha256(BASE_PATH.read_bytes()).hexdigest() != BASE_SHA256:
    raise RuntimeError('Reviewed Flipper bench helper changed; new review required')
spec = importlib.util.spec_from_file_location('minus20_private_bench', BASE_PATH)
BENCH = importlib.util.module_from_spec(spec)
spec.loader.exec_module(BENCH)
BENCH.REMOTE_DIR = '/ext/subghz/stratolink-ctt-minus20-20261009-v1'
BENCH.FIXTURE_DIR = HERE / 'fixtures/flipper_ctt/minus20'
BENCH.HASHES = {FIXTURE_NAME: FIXTURE_SHA256}
_validate_fixtures = BENCH.validate_fixtures
_make_plan = BENCH.make_plan
_loaded_self_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def validate_fixtures(fixtures):
    _validate_fixtures(fixtures)
    original = ORIGINAL.read_bytes()
    if BENCH.digest(BASE_PATH.read_bytes()) != BASE_SHA256 or BENCH.digest(original) != ORIGINAL_SHA256:
        raise BENCH.BenchError('Pinned base helper or original fixture changed')
    marker = b'Custom_preset_data: '
    rows = [line for line in original.splitlines() if line.startswith(marker)]
    if len(rows) != 1:
        raise BENCH.BenchError('Original preset is ambiguous')
    preset = bytearray.fromhex(rows[0][len(marker):].decode('ascii'))
    if len(preset) != 46 or preset[36:39] != bytes.fromhex('00 00 12'):
        raise BENCH.BenchError('Original preset PA-table boundary changed')
    preset[38] = 0x0e
    changed_line = marker + preset.hex(' ').upper().encode('ascii')
    if fixtures[FIXTURE_NAME] != original.replace(rows[0], changed_line, 1):
        raise BENCH.BenchError('Only PATABLE byte38 0x12 to 0x0E may change')


def make_plan(args):
    plan = _make_plan(args)
    if BENCH.digest(Path(__file__).read_bytes()) != _loaded_self_sha256:
        raise BENCH.BenchError('Adapter changed since loading')
    plan['minus20_diagnostic'] = {
        'adapter_sha256': _loaded_self_sha256,
        'base_helper_sha256': BASE_SHA256,
        'original_fixture_sha256': ORIGINAL_SHA256,
        'fixture_sha256': FIXTURE_SHA256,
        'preset_delta': {'byte_index': 38, 'before': 18, 'after': 14},
        'nominal_tx_dbm': -20,
        'calibrated_power': False,
        'conditional_use': 'Operator-reviewed RX/no-IRQ diagnostic only; not a receiver fix or flight qualification',
        'power_source': 'Official Flipper1.3.4 ad2a80042349a0cc6e0a14541e985d798a89f389 cc1101_configs.c:213',
    }
    return plan


BENCH.validate_fixtures = validate_fixtures
BENCH.make_plan = make_plan


def main(argv=None):
    return BENCH.main(argv)


if __name__ == '__main__':
    raise SystemExit(main())
