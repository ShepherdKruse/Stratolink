#!/usr/bin/env python3
"""Run the explicit offline tooling suite, never operator or hardware commands."""

import argparse
import os
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
TESTS = (
    "evidence_provenance_test.py",
    "portable_tools_test.py",
    "preserve_board1_baseline_test.py",
    "flash_board1_development_test.py",
    "decode_flight_state_test.py",
    "board1_provisioning_audit_test.py",
    "provision_board1_ttn_regions_test.py",
    "merge_board1_regional_header_test.py",
    "install_board1_regional_formatter_test.py",
    "provision_board1_launch_authority_test.py",
    "ttn_devnonce_audit_test.py",
    "ttn_storage_replay_test.py",
    "ttn_storage_presence_audit_test.py",
    "ttn_uplink_archive_test.py",
    "ttn_decoded_comparison_test.py",
    "export_supabase_soak_test.py",
    "stratolink1_bringup_delivery_audit_test.py",
    "ttn_downlink_queue_test.py",
    "ttn_soak_monitor_lifecycle_test.py",
    "telemetry_liveness_wire_test.py",
    "server_liveness_recovery_integration_test.py",
    "supabase_schema_probe_test.py",
    "meshtastic_hil_stimulus_test.py",
    "meshtastic_passive_monitor_test.py",
    "validate_meshtastic_hil_test.py",
    "validate_meshtastic_passive_test.py",
    "b2b_rf_two_node_hil_test.py",
    "ctt_two_node_hil_test.py",
    "flipper_ctt_bench_20261009_test.py",
    "flipper_ctt_minus20_bench_20261009_test.py",
    "flipper_ctt_minus20_bad_bench_20261009_test.py",
    "flipper_ctt_iq_test_20261009_test.py",
    "auxiliary_rx_energy_audit_test.py",
    "class_a_energy_audit_test.py",
    "gps_backup_energy_audit_test.py",
    "dynamic_memory_source_contract_test.py",
    "dynamic_memory_gnss_contract_test.py",
    "static_stack_usage_audit_test.py",
    "mission_energy_store_sizing_audit_test.py",
    "radio_sleep_fault_energy_audit_test.py",
    "vendor_balanced_module_screen_test.py",
    "supercap_balance_audit_test.py",
    "supercap_charge_ceiling_audit_test.py",
    "supercap_night_reserve_audit_test.py",
    "launch_darkness_envelope_audit_test.py",
    "low_rail_load_audit_test.py",
    "regional_airtime_audit_test.py",
    "rf_module_band_audit_test.py",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="print names without running")
    args = parser.parse_args()
    if args.list:
        print("\n".join(TESTS))
        return 0
    failed = []
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    for name in TESTS:
        try:
            result = subprocess.run(
                [sys.executable, str(HERE / name)], cwd=HERE.parents[1],
                env=env, capture_output=True, text=True, timeout=180,
            )
        except subprocess.TimeoutExpired:
            failed.append(name)
            print(f"FAIL {name}: exceeded 180 seconds", flush=True)
            continue
        print(f"{'PASS' if result.returncode == 0 else 'FAIL'} {name}", flush=True)
        if result.returncode:
            failed.append(name)
            print(result.stdout + result.stderr, flush=True)
    print(f"{len(TESTS) - len(failed)}/{len(TESTS)} offline modules passed", flush=True)
    return int(bool(failed))


if __name__ == "__main__":
    raise SystemExit(main())
