#!/usr/bin/env bash
set -euo pipefail

# Compile every pure flight-logic suite with warnings-as-errors plus ASan and
# UBSan, then execute it from a fresh temporary directory. This is deliberately
# independent of PlatformIO so the same wire/state logic is checked by a second
# compiler/runtime.

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/stratolink-host-tests.XXXXXX")"
trap 'rm -rf -- "$build_dir"' EXIT

compiler="${CXX:-c++}"
common_flags=(
  -std=c++17
  -Wall
  -Wextra
  -Werror
  -pedantic
  -fno-omit-frame-pointer
  -fsanitize=address,undefined
  -I "$repo_dir/firmware/include"
  -I "$repo_dir/firmware/src"
)

run_suite() {
  local name="$1"
  shift
  "$compiler" "${common_flags[@]}" "$@" -o "$build_dir/$name"
  # Apple's bundled ASan does not implement LeakSanitizer; address and
  # undefined-behaviour instrumentation remain fully enabled.
  ASAN_OPTIONS=detect_leaks=0 UBSAN_OPTIONS=halt_on_error=1 \
    "$build_dir/$name"
}

run_suite b2b_id_store \
  "$repo_dir/firmware/test/test_b2b_id_store.cpp" \
  "$repo_dir/firmware/src/b2b_id_store.cpp"
run_suite b2b_wire \
  "$repo_dir/firmware/test/test_b2b_wire.cpp" \
  "$repo_dir/firmware/src/b2b.cpp" \
  "$repo_dir/firmware/src/crypto_aes128.cpp"
run_suite command \
  "$repo_dir/firmware/test/test_command.cpp" \
  "$repo_dir/firmware/src/command.cpp"
run_suite command_sequence_store \
  "$repo_dir/firmware/test/test_command_sequence_store.cpp" \
  "$repo_dir/firmware/src/command_sequence_store.cpp"
run_suite crypto_aes128 \
  "$repo_dir/firmware/test/test_crypto_aes128.cpp" \
  "$repo_dir/firmware/src/crypto_aes128.cpp"
run_suite ctt_decode \
  "$repo_dir/firmware/test/test_ctt_decode.cpp" \
  "$repo_dir/firmware/src/ctt_decode.cpp"
run_suite ctt_event \
  "$repo_dir/firmware/test/test_ctt_event.cpp" \
  "$repo_dir/firmware/src/ctt_event.cpp"
run_suite ctt_queue \
  "$repo_dir/firmware/test/test_ctt_queue.cpp" \
  "$repo_dir/firmware/src/ctt_queue.cpp"
run_suite ctt_test_tag \
  "$repo_dir/firmware/test/test_ctt_test_tag.cpp"
run_suite devnonce_store \
  "$repo_dir/firmware/test/test_devnonce_store.cpp" \
  "$repo_dir/firmware/src/devnonce_store.cpp"
run_suite gps_freshness \
  "$repo_dir/firmware/test/test_gps_freshness.cpp" \
  "$repo_dir/firmware/src/gps_freshness.cpp"
run_suite gps_pvt_validation \
  "$repo_dir/firmware/test/test_gps_pvt_validation.cpp" \
  "$repo_dir/firmware/src/gps_pvt_validation.cpp"
run_suite gps_backup_policy \
  "$repo_dir/firmware/test/test_gps_backup_policy.cpp" \
  "$repo_dir/firmware/src/gps_backup_policy.cpp"
run_suite lorawan_counter \
  "$repo_dir/firmware/test/test_lorawan_counter.cpp" \
  "$repo_dir/firmware/src/lorawan_counter.cpp"
run_suite lorawan_crypto \
  "$repo_dir/firmware/test/test_lorawan_crypto.cpp" \
  "$repo_dir/firmware/src/lorawan_crypto.cpp" \
  "$repo_dir/firmware/src/crypto_aes128.cpp"
run_suite lorawan_frame \
  "$repo_dir/firmware/test/test_lorawan_frame.cpp" \
  "$repo_dir/firmware/src/lorawan_frame.cpp" \
  "$repo_dir/firmware/src/lorawan_counter.cpp" \
  "$repo_dir/firmware/src/lorawan_crypto.cpp" \
  "$repo_dir/firmware/src/crypto_aes128.cpp"
run_suite lis2dh12_conversion \
  "$repo_dir/firmware/test/test_lis2dh12_conversion.cpp"
run_suite ltr390_conversion \
  "$repo_dir/firmware/test/test_ltr390_conversion.cpp"
run_suite meshtastic_relay_mac \
  "$repo_dir/firmware/test/test_meshtastic_relay_mac.cpp" \
  "$repo_dir/firmware/src/meshtastic_relay_mac.cpp"
run_suite mic_noise_ema \
  "$repo_dir/firmware/test/test_mic_noise_ema.cpp"
run_suite ms5611_crc \
  "$repo_dir/firmware/test/test_ms5611_crc.cpp" \
  "$repo_dir/firmware/src/ms5611_crc.cpp"
run_suite ms5611_compensation \
  "$repo_dir/firmware/test/test_ms5611_compensation.cpp" \
  "$repo_dir/firmware/src/ms5611_compensation.cpp"
run_suite optical_fault_policy \
  "$repo_dir/firmware/test/test_optical_fault_policy.cpp"
run_suite power_adc_policy \
  "$repo_dir/firmware/test/test_power_adc_policy.cpp"
run_suite region \
  "$repo_dir/firmware/test/test_region.cpp" \
  "$repo_dir/firmware/src/region_manager.cpp"
run_suite reset_cause \
  "$repo_dir/firmware/test/test_reset_cause.cpp" \
  "$repo_dir/firmware/src/reset_cause.cpp"
run_suite stop1_progress_policy \
  "$repo_dir/firmware/test/test_stop1_progress_policy.cpp"
run_suite tamp_record \
  "$repo_dir/firmware/test/test_tamp_record.cpp"
run_suite telemetry_v2 \
  "$repo_dir/firmware/test/test_telemetry_v2.cpp" \
  "$repo_dir/firmware/src/telemetry.cpp"
run_suite tmp117_conversion \
  "$repo_dir/firmware/test/test_tmp117_conversion.cpp"
run_suite temperature_wire \
  "$repo_dir/firmware/test/test_temperature_wire.cpp" \
  "$repo_dir/firmware/src/telemetry.cpp"

printf 'All 31 strict ASan/UBSan host suites passed.\n'
