# StratoLink-2 exact-candidate post-soak HIL

## Current qualification checkpoint, 2026-07-28

The historical retry narrative below is retained because failed handoffs are
part of the evidence chain. The controlling current checkpoint is newer:

- Retry-3 completed 86,400.113 seconds at 4,660 mV with zero reconnects,
  maximum control gap 30.523 seconds, and 69 contiguous TTN uplinks.
- Flight candidate v15 is the exact installed image. Its ELF is 239,736 bytes,
  SHA-256 `8fa10da859b2c542d244cb2f62bebcf388730cbeea9eb4746a94c2d50e3d91f8`.
  Its BIN is 132,956 bytes, SHA-256
  `920f57c139236b6097caec8936cefe681f82fa3b4c4e084f2861ad54bd1ae20d`.
  The immutable v15 verifier has zero failures.
- The final restore manifest proves the exact v15 flash and byte-identical
  preservation of the 4 KiB DevNonce journal. The journal has four valid
  records, highest nonce 3, next nonce 4, zero invalid records, and ample
  remaining capacity.
- The exact v15 image joined US915 and produced four fresh contiguous uplinks,
  FCntUp 0 through 3. A second controlled command test consumed one queued
  fPort-10 PING with sequence 160, persisted that sequence and relay state in
  TAMP, advanced FCntDown, and emitted `command_ack_seq=160` on the next
  telemetry-v2 uplink. The TTN downlink queue was empty afterward.
- The profile image measured 6.730 uA median in the terminal STOP1 phase. The
  exact v15 image measured 6.688 uA median across its five terminal 5 s bins.
  Every selected bin was below 10 uA and the medians differed by 0.042 uA.
- A fresh receive-only 60 s SDR capture at 906.875 MHz found 31 bursts,
  including three LongFast-duration candidates. The earlier protocol-level
  3,600.756 s passive run observed 50 live packets from 12 opaque sources.

This checkpoint closes the single-board pre-supercap power, exact-image
LoRaWAN, durable command, and local-stimulus gates. It does not replace the
remaining physical tests: fitted-store endurance and cold behavior,
clear-sky GNSS, two-node B2B and CTT emulation, exact-assembly antenna sweep,
or production backend deployment and registration.

This sequence begins only after the precursor soak has a clean `hold_end` and
the standby PPK2 supervisor has acquired at 4660 mV with a heartbeat. It binds
all J-Link reads to the exact flight ELF and keeps the PPK2 as the payload
power source throughout.

## Active retry evidence

The first primary power log completed 57,600.160 s cleanly, but its standby
had been launched without macOS device permission and did not assert the PPK2
until 149.047 s after `hold_end`. That attempt is intentionally preserved as
`stratolink2_soak_20260724_failed_handoff.json` and is not acceptable for the
gates below. The active retry uses:

```text
primary: stratolink2_soak_retry_20260725_power.jsonl
standby: stratolink2_soak_retry_20260725_handoff.jsonl
TTN:     stratolink2_soak_retry_20260725_ttn.jsonl
```

The retry standby is `ppk2_power_handoff.py`, launched with the required device
permission. It does not import the PPK driver, create the standby log, or open
the serial port until the primary log contains exactly one validated
`hold_end` at or beyond 57,600 s. This replaces the invalid assumption that a
macOS CDC serial open is exclusive.

The post-retry preservation hold completed one 86,400.119-second hold at
4,660 mV with zero reconnects and valid assertion gaps. Its queued seven-day
supervisor then failed before PPK2 access because its interpreter lacked
`pyserial`; no extension log was created. A rescue supervisor acquired only
after 110.049 seconds, not the required 0-2 seconds. The immutable record is
`stratolink2_soak_retry_20260725_failed_extension_handoff_20260727.json`.
This attempt is failed evidence and prohibits precursor preservation, J-Link
access, halt, reset, or flash. Do not run the commands below against this run.

For a **new clean retry**, the standby must finish exactly one 86,400-second
hold, and a dependency-preflighted seven-day supervisor launched from
`analysis/.venv/bin/python` must acquire 0-2 seconds later at 4,660 mV with
zero reconnects and emit a later heartbeat. During that live hold, use this
read-only command to detect source, reconnect, timestamp, or heartbeat-gap
failure early:

```text
new primary:   stratolink2_soak_retry2_20260727_power.jsonl
new standby:   stratolink2_soak_retry2_20260727_handoff.jsonl
new TTN:       stratolink2_soak_retry2_20260727_ttn.jsonl
primary start: 2026-07-27T09:47:54.388Z
```

The primary is configured for 86,400 seconds and the already queued standby
for seven days. Both use the project virtual environment; the standby passed
its non-mutating dependency preflight before entering its wait loop. Substitute
these new paths in the commands below; the older filenames remain only as a
record of the failed attempt.

The retry-2 MQTT collector connected at `2026-07-27T10:37:56.444Z`, after the
fresh power holder began. It writes only the new retry-2 path and must never
append to the frozen 20260725 TTN log. The already observed first post-reset
uplink is independently preserved by TTN Storage and Supabase evidence. Final
relay-soak qualification uses the retry-2 collector's own contiguous interval;
do not splice older MQTT bytes into it. Use a read-only Storage query only to
document the short pre-collector interval separately. That query now passes as
`stratolink2_retry2_precollector_storage_20260727.json`: it binds exactly two
rows, FCntUp 1 at `10:01:35.832312164Z` and FCntUp 2 at
`10:22:34.691985303Z`, with no other-device rows. The live collector then
captured FCntUp 3 at `10:43:33.609014264Z`.

```sh
analysis/.venv/bin/python analysis/diagnostics/power_extension_summary.py \
  --primary analysis/diagnostics/logs/stratolink2_soak_retry2_20260727_power.jsonl \
  --extension analysis/diagnostics/logs/stratolink2_soak_retry2_20260727_handoff.jsonl
```

Immediately after the extension's first heartbeat, freeze the completed primary
and the then-current append-only extension prefix in a create-once report:

```sh
analysis/.venv/bin/python analysis/diagnostics/power_extension_summary.py \
  --primary analysis/diagnostics/logs/stratolink2_soak_retry2_20260727_power.jsonl \
  --extension analysis/diagnostics/logs/stratolink2_soak_retry2_20260727_handoff.jsonl \
  --final \
  --output analysis/diagnostics/logs/stratolink2_soak_retry2_20260727_handoff_summary.json
```

The final command requires exactly one primary `power_on` and `hold_end`, at
least 86,400 seconds held, 4,660 mV throughout, zero reconnects, and every
assertion and terminal gap at or below 31.5 seconds. It also requires the
extension transition within 0-2 seconds and a later heartbeat under the same
source/reconnect/gap rules. Run it promptly: an extension `hold_end` is rejected
because this evidence is designed to capture the live seven-day hold, not to
retroactively certify it after power supervision ends. Passing proves only
PPK2 supervisor command continuity—not VSTOR/3V3 continuity, payload execution,
or absence of a no-supercap reset.

At retry completion, pass the explicit retry-2 paths to every gate. Use
`stratolink2_soak_retry2_20260727_final.json`,
`stratolink2_soak_retry2_20260727_sensor_model.json`, and a retry-2-specific
Supabase export. The create-once preservation and flash wrappers already expose
`--summary`, `--sensor-model`, `--handoff-power`, `--prefix`, and
`--precursor-manifest`; do not fall back to their first-attempt defaults.

After stopping and freezing only the retry TTN collector, use these exact
non-mutating gates:

Both final telemetry consumers must independently enforce the same two VSTOR
bounds: the PPK2-supported floor is `4660 - 100 = 4560 mV`, while the
harvester ceiling is `5363 + 75 = 5438 mV`. A passing source floor cannot
excuse an excessive harvester peak, and a safe peak cannot excuse a low rail.

```sh
python3 analysis/diagnostics/regional_airtime_audit.py \
  --output analysis/diagnostics/logs/stratolink2_regional_airtime_20260726.json

# This currently emits a deliberate blocked result: the exact 1% charge
# divider lacks a provable 5.5 V absolute-maximum margin. Preserve the JSON;
# --allow-blocked changes only the process exit, never the result.
analysis/.venv/bin/python analysis/diagnostics/supercap_charge_ceiling_audit.py \
  --allow-blocked \
  --ttn analysis/diagnostics/logs/stratolink2_soak_retry2_20260727_ttn.jsonl \
  --output analysis/diagnostics/logs/stratolink2_supercap_charge_ceiling_retry2_20260728.json

# This also emits a deliberate blocked result. The planned capacitor is
# specified at 0.8-1.2 F; even the baseline-only room screen does not reach
# 12 h at 0.8 F when 35 uA sleep and 6 uA capacitor leakage are combined.
python3 analysis/diagnostics/supercap_night_reserve_audit.py \
  --allow-blocked \
  --output analysis/diagnostics/logs/stratolink2_supercap_night_reserve_20260726.json

# Bind the Flight-3 mean reconstruction to the direct-sun horizon. Its longest
# complete clear-sky geometric night is 9.674 h. Both screened safer dividers
# fall short even before active work: 7.50 MOhm by 0.348 h and 7.32 MOhm by
# 0.767 h. This remains blocked and only sizes the minimum darkness HIL.
python3 analysis/diagnostics/flight3_darkness_audit.py \
  --allow-blocked \
  --output analysis/diagnostics/logs/stratolink3_darkness_audit_20260726.json

# Bound launch-season growth at the highest accepted Flight-3 latitude/altitude.
# For the planned 2026-07-31 launch, clear-sky night is already 8.667 h and
# grows to 10.091 h within 30 days and 13.252 h within 90 days. The 7.32 MOhm
# minimum-cap baseline is exceeded on 2026-08-07 and the 7.50 MOhm reference
# on 2026-08-16, before active work or weather losses are included.
python3 analysis/diagnostics/launch_darkness_envelope_audit.py \
  --allow-blocked \
  --output analysis/diagnostics/logs/stratolink2_friday_darkness_envelope_20260727.json

# Add only the already-source-bound typical hot-GNSS, primary-TX, and empty
# Class-A receive energy to the continuous-current screen. This lower bound
# still omits sensors, WFI MCU current, joins, retries, cold, aging, weather,
# sag, and reserve. At the full tolerance-lower charge corner, the 0.8 F part
# reaches the 3.32 V accounting floor in 3.509 h with 7.32 MOhm and 3.798 h
# with 7.50 MOhm. Launch night alone requires at least 1.822/1.779 F before
# the omitted terms; the 90-day seasonal screen requires 2.764/2.662 F.
python3 analysis/diagnostics/mission_energy_store_sizing_audit.py \
  --allow-blocked \
  --output analysis/diagnostics/logs/stratolink2_mission_energy_store_sizing_20260727_v3.json

# This is a third deliberate hardware block: the exact dual-cell C5 footprint
# leaves its balance terminal open, while CAP-XX does not provide internal
# balancing and recommends balancing for every series-connected module.
python3 analysis/diagnostics/supercap_balance_audit.py \
  --allow-blocked \
  --output analysis/diagnostics/logs/stratolink2_supercap_balance_20260726.json

python3 analysis/diagnostics/gps_backup_energy_audit.py \
  --output analysis/diagnostics/logs/gps_backup_energy_audit_20260726_min_cap.json

SUPABASE_PUBLISHABLE_KEY='<private runtime value>' \
analysis/.venv/bin/python analysis/diagnostics/export_supabase_soak.py \
  --since 2026-07-27T10:37:56Z \
  --through-ttn-log analysis/diagnostics/logs/stratolink2_soak_retry2_20260727_ttn.jsonl \
  --output analysis/diagnostics/logs/stratolink2_soak_retry2_20260727_supabase.json

analysis/.venv/bin/python analysis/diagnostics/soak_summary.py \
  --power analysis/diagnostics/logs/stratolink2_soak_retry2_20260727_power.jsonl \
  --handoff-power analysis/diagnostics/logs/stratolink2_soak_retry2_20260727_handoff.jsonl \
  --ttn analysis/diagnostics/logs/stratolink2_soak_retry2_20260727_ttn.jsonl \
  --supabase analysis/diagnostics/logs/stratolink2_soak_retry2_20260727_supabase.json \
  --firmware-profile relay_soak \
  --expected-source-mv 4660 \
  --vbat-ov-mv 5363 \
  --vbat-ov-tolerance-mv 75 \
  --min-held-seconds 86400 \
  --final \
  --output analysis/diagnostics/logs/stratolink2_soak_retry2_20260727_final.json

analysis/.venv/bin/python analysis/diagnostics/soak_sensor_model.py \
  --ttn analysis/diagnostics/logs/stratolink2_soak_retry2_20260727_ttn.jsonl \
  --source-mv 4660 \
  --vbat-ov-mv 5363 \
  --vbat-ov-tolerance-mv 75 \
  --output analysis/diagnostics/logs/stratolink2_soak_retry2_20260727_sensor_model.json

MPLCONFIGDIR=/private/tmp/stratolink-mpl analysis/.venv/bin/python \
  analysis/diagnostics/plot_final_soak.py \
  --power analysis/diagnostics/logs/stratolink2_soak_retry2_20260727_power.jsonl \
  --handoff-power analysis/diagnostics/logs/stratolink2_soak_retry2_20260727_handoff.jsonl \
  --ttn analysis/diagnostics/logs/stratolink2_soak_retry2_20260727_ttn.jsonl \
  --summary analysis/diagnostics/logs/stratolink2_soak_retry2_20260727_final.json \
  --output analysis/diagnostics/stratolink2_final_soak_retry2_20260728.png

MPLCONFIGDIR=/private/tmp/stratolink-mpl analysis/.venv/bin/python \
  analysis/diagnostics/plot_launch_readiness.py \
  --matrix analysis/diagnostics/STRATOLINK2_LAUNCH_READINESS_20260724.md \
  --output analysis/diagnostics/stratolink2_launch_readiness_retry2_20260728.png
```

The unversioned, v2, and v3 retry-readiness PNGs were generated from earlier
evidence states. They are preserved as superseded intermediates and must not be
passed to precursor preservation. Only the create-once retry-2 image above,
generated after the retry-2 final summary and sensor model pass, is eligible as
the matrix-bound readiness artifact.

The connected Supabase app was rechecked on 2026-07-26 and exposes only the
unrelated `pegboard` project (`wznuxiysfirtcyvfrvdb`), not StratoLink's
explicit REST project (`iazmnyyfsobucndqncgw`). Do not silently substitute the
connector project. Run the create-once exporter against its compiled-in exact
StratoLink URL with the publishable key supplied only through
`SUPABASE_PUBLISHABLE_KEY`; do not use or log the secret/service key for this
public parity read.

Only after those outputs pass and share the exact retry TTN provenance,
complete **Immutable candidate** below without target access. Require its
create-once v11 verification report to pass, then return here and use the
explicit create-once preservation arguments. The preservation wrapper binds
that report and will reject a missing, failed, or superseded candidate:

```sh
python3 analysis/diagnostics/preserve_precursor.py \
  --prefix analysis/diagnostics/logs/stratolink2_retry_precursor_20260726 \
  --summary analysis/diagnostics/logs/stratolink2_soak_retry2_20260727_final.json \
  --sensor-model analysis/diagnostics/logs/stratolink2_soak_retry2_20260727_sensor_model.json \
  --candidate-verification analysis/diagnostics/logs/stratolink2_flight_candidate_verification_20260728_v11.json \
  --handoff-power analysis/diagnostics/logs/stratolink2_soak_retry2_20260727_handoff.jsonl \
  --primary-power analysis/diagnostics/logs/stratolink2_soak_retry2_20260727_power.jsonl \
  --ttn analysis/diagnostics/logs/stratolink2_soak_retry2_20260727_ttn.jsonl \
  --supabase analysis/diagnostics/logs/stratolink2_soak_retry2_20260727_supabase.json \
  --soak-plot analysis/diagnostics/stratolink2_final_soak_retry2_20260728.png \
  --readiness-plot analysis/diagnostics/stratolink2_launch_readiness_retry2_20260728.png \
  --candidate-elf firmware/.pio/build/stratolink/firmware.elf \
  --candidate-bin firmware/.pio/build/stratolink/firmware.bin \
  --pre-retry-flash firmware/.pio/precursor_evidence/stratolink2_pre_retry_flash_20260724.bin \
  --check-only

python3 analysis/diagnostics/preserve_precursor.py \
  --prefix analysis/diagnostics/logs/stratolink2_retry_precursor_20260726 \
  --summary analysis/diagnostics/logs/stratolink2_soak_retry2_20260727_final.json \
  --sensor-model analysis/diagnostics/logs/stratolink2_soak_retry2_20260727_sensor_model.json \
  --candidate-verification analysis/diagnostics/logs/stratolink2_flight_candidate_verification_20260728_v11.json \
  --handoff-power analysis/diagnostics/logs/stratolink2_soak_retry2_20260727_handoff.jsonl \
  --primary-power analysis/diagnostics/logs/stratolink2_soak_retry2_20260727_power.jsonl \
  --ttn analysis/diagnostics/logs/stratolink2_soak_retry2_20260727_ttn.jsonl \
  --supabase analysis/diagnostics/logs/stratolink2_soak_retry2_20260727_supabase.json \
  --soak-plot analysis/diagnostics/stratolink2_final_soak_retry2_20260728.png \
  --readiness-plot analysis/diagnostics/stratolink2_launch_readiness_retry2_20260728.png \
  --candidate-elf firmware/.pio/build/stratolink/firmware.elf \
  --candidate-bin firmware/.pio/build/stratolink/firmware.bin \
  --pre-retry-flash firmware/.pio/precursor_evidence/stratolink2_pre_retry_flash_20260724.bin
```

Pass the same explicit retry summary, sensor model, standby log, and resulting
`stratolink2_retry_precursor_20260726_manifest.json` to both invocations of
`flash_flight_candidate.py`. A default-path invocation is a hard stop for the
retry.

## Immutable candidate

Do not assign the next version number from the current incremental build
directory. After the final source review is closed, execute this local-only
freeze sequence. None of these commands accesses the target:

```sh
set -euo pipefail
git diff --check
/Users/twarn/.platformio/penv/bin/pio run -d firmware
/Users/twarn/.platformio/penv/bin/pio run -d firmware -e stratolink -t compiledb
python3 analysis/diagnostics/warning_compile.py --analyzer
analysis/diagnostics/run_host_suites.sh
SKIP_STALE_CANDIDATE_VERIFICATION=1 \
  analysis/diagnostics/run_diagnostic_tests.sh
(cd web && npm run verify && npm run build)

python3 analysis/diagnostics/dynamic_memory_audit.py \
  --elf firmware/.pio/build/stratolink/firmware.elf \
  --output analysis/diagnostics/logs/stratolink2_flight_candidate_dynamic_memory_20260728_v11.json

python3 analysis/diagnostics/static_stack_usage_audit.py \
  --compiledb firmware/compile_commands.json \
  --elf firmware/.pio/build/stratolink/firmware.elf \
  --output analysis/diagnostics/logs/stratolink2_flight_candidate_static_stack_20260728_v11.json

stratolink_v11_build_dir="$(mktemp -d /private/tmp/stratolink-flight-v11-independent.XXXXXX)"
PLATFORMIO_BUILD_DIR="$stratolink_v11_build_dir" \
  /Users/twarn/.platformio/penv/bin/pio run -d firmware -e stratolink

python3 analysis/diagnostics/draft_flight_candidate_identity.py \
  --independent-elf "$stratolink_v11_build_dir/stratolink/firmware.elf" \
  --independent-bin "$stratolink_v11_build_dir/stratolink/firmware.bin" \
  --output analysis/diagnostics/logs/stratolink2_flight_candidate_identity_20260728_v11.json
```

The identity tool refuses overwrite, requires byte-identical canonical and
independent ELF/BIN files, rejects every bench/diagnostic marker, requires all
firmware inputs to predate both builds, compares section and required-symbol
layouts, and emits the exact eight static verifier bindings. Its passing
report is a **draft**, not authorization to flash.

Review those values, update all `EXPECTED_*` bindings in
`verify_flight_candidate.py`, and regenerate the seven checked worktree HIL
files from the canonical artifacts:

```sh
python3 analysis/diagnostics/generate_flight_hil.py \
  --elf firmware/.pio/build/stratolink/firmware.elf \
  --bin firmware/.pio/build/stratolink/firmware.bin \
  --out-dir analysis/diagnostics/generated

python3 analysis/diagnostics/verify_flight_candidate.py \
  --dynamic-memory-audit analysis/diagnostics/logs/stratolink2_flight_candidate_dynamic_memory_20260728_v11.json \
  --static-stack-audit analysis/diagnostics/logs/stratolink2_flight_candidate_static_stack_20260728_v11.json
analysis/diagnostics/run_diagnostic_tests.sh
git diff --check
```

The first verifier run is intentionally stdout-only. It must pass with zero
failures, and every non-mutating diagnostic regression must then pass. If any
test changes a firmware/configuration input or rebuilds a different flight
artifact, restart the freeze sequence. Only then create the immutable report:

```sh
python3 analysis/diagnostics/verify_flight_candidate.py \
  --dynamic-memory-audit analysis/diagnostics/logs/stratolink2_flight_candidate_dynamic_memory_20260728_v11.json \
  --static-stack-audit analysis/diagnostics/logs/stratolink2_flight_candidate_static_stack_20260728_v11.json \
  --output \
  analysis/diagnostics/logs/stratolink2_flight_candidate_verification_20260728_v11.json
```

The create-once verifier regenerates the HIL manifest/scripts into a temporary directory
and byte-compares all seven outputs, rejects any firmware/configuration input
newer than the ELF, scans both artifacts for bench/diagnostic markers, verifies
51 exact HIL symbols and fixed memory/section sizes, and requires the
create-once dynamic-memory and static-stack reports to pass against that exact
ELF. It binds the candidate, both memory reports, source inputs, and generated
scripts with SHA-256 provenance. Candidate v9 and all earlier hashes are
superseded. Require the new v11 report to pass with zero failures, then record
the exact ELF/BIN hashes it emits. Do not predeclare or reuse an older hash.

Any later source edit or hash change invalidates v11 and requires all 13
PlatformIO builds, strict/sanitized host suites, web-vector parity, and a new
set of frozen hashes plus a regenerated manifest before flash.

## 1. Preserve the precursor soak

1. Do not attach, halt, reset, or flash the target until the retry-2 primary
   PPK2 log contains exactly one `hold_end` reporting at least 86,400 s and the standby
   supervisor has acquired at 4660 mV within 0-2 s with at least one later
   heartbeat. Require zero reconnects and no control gap—including the final
   primary assertion-to-`hold_end` interval—above 31.5 s.
2. After the handoff evidence above exists, stop only the
   `ttn_soak_monitor.py` collector with `SIGINT`, wait for that exact process to
   exit, and verify that no process still has the TTN JSONL open for writing.
   Record its terminal byte length and SHA-256. Do not freeze the final summary
   while the collector is still able to append: one later uplink would
   correctly invalidate the byte-exact provenance and block precursor
   preservation.
3. Refresh the read-only production Supabase export after the TTN monitor has
   recorded its last soak uplink, then run the explicit retry-specific export
   and `soak_summary.py --firmware-profile relay_soak --final` commands in
   **Active retry evidence** above. Do not use the summary tool's first-attempt
   defaults.

   A nonzero exit is a hard stop: preserve the report and diagnose without
   flashing or resetting the MCU. The passing report records byte length and
   SHA-256 for every input. Power, TTN, and Supabase inputs must remain exact;
   only the still-running standby log may grow, and its recorded prefix must
   remain byte-identical.
4. Quantify the complete decoded sensor stream with the explicit retry TTN and
   retry output paths in **Active retry evidence** above. Do not use the sensor
   tool's first-attempt defaults.

   A nonzero exit is also a hard stop. This gate proves completeness,
   continuity, room-condition plausibility, VSTOR stability, stationary
   acceleration, optical day/night coherence, and strict no-fix field
   consistency. It explicitly does not replace chamber, calibrated
   UV/acoustic, clear-sky GNSS, or supercap qualification.
   Its TTN-input provenance must match the final summary exactly.
5. Generate the final soak and overall-readiness graphics only from the
   preserved passing JSON and current evidence matrix. A graphic must never
   turn a missing or stale final summary into a pass label.
6. The original precursor ELF was overwritten by a later compile and must not
   be confused with the current
   `firmware/.pio/build/stratolink_soak/firmware.elf`. The preserved
   `jlink_read_soak_health.jlink` script predates that rebuild and contains the
   actual pre-rebuild symbol addresses; its address shifts relative to the
   current ELF independently confirm that provenance.
   A complete 256 KiB target-flash baseline captured during the earlier run,
   before the clean retry, is preserved at the ignored path
   `firmware/.pio/precursor_evidence/stratolink2_pre_retry_flash_20260724.bin`
   with SHA-256
   `fd6ed6053206ddfe63ab40c7333752b383ad5f71caa07af3c334e5da4d5891f9`.
   This is a pre-**retry** baseline, not a pre-first-run image. The preservation
   wrapper validates that fixed hash before target access and requires the
   post-soak 256 KiB dump to match it byte-for-byte. A mismatch proves flash
   mutation during the clean retry (for example a hidden OTAA/DevNonce
   reservation) and blocks every reset or flash action.
7. Now that the non-invasive gates are frozen, run both complete, explicit
   `preserve_precursor.py` commands in **Active retry evidence** above. A bare
   or default-path invocation is forbidden for this retry.

   It selects J-Link serial `802007563`, saves complete 256 KiB flash and
   64 KiB RAM images, captures FLASH OPTR, prints all 20 physical TAMP words, reads the
   known precursor health counters, resumes the MCU after each halt, validates
   dump sizes, and writes raw J-Link output plus SHA-256 hashes into a manifest.
   OPTR bit 17 (`IWDG_STOP`) must be set, proving the watchdog actually runs in
   STOP1 as assumed by the 28 s RTC/watchdog containment proof. It refuses any
   existing final or partial artifact rather than overwriting the only
   pre-flash state.
8. Copy the power, handoff-power, TTN JSONL logs, Supabase export, atomic final
   JSON summary,
   and sensor-model JSON into the evidence bundle before modifying the board.

## 2. Verify the preserved pre-flash retained state

Do not perform another direct J-Link read here. The create-once precursor
wrapper in section 1 already captured complete 256 KiB flash, 64 KiB RAM,
FLASH OPTR, all 20 physical TAMP words, and the precursor health counters under the live
PPK2 gate. Require its manifest to identify and hash all six artifacts and to
report `iwdg_runs_in_stop: true`. The full flash
dump contains both reserved DevNonce pages at `0x0803F000-0x0803FFFF`; the
flash wrapper's `--check-only` path revalidates that dump and every other
precursor record before permitting any write. A second unguarded read would
add target-access risk without adding independent evidence. Do not mass-erase
the MCU.

## 3. Flash and byte-verify the exact candidate

Run `flash_flight_candidate.py` first with `--check-only` and then without it,
passing all of the following explicit paths on both invocations:

```sh
python3 analysis/diagnostics/flash_flight_candidate.py \
  --prefix analysis/diagnostics/logs/stratolink2_flight_flash_20260728_v11 \
  --summary analysis/diagnostics/logs/stratolink2_soak_retry2_20260727_final.json \
  --sensor-model analysis/diagnostics/logs/stratolink2_soak_retry2_20260727_sensor_model.json \
  --candidate-verification analysis/diagnostics/logs/stratolink2_flight_candidate_verification_20260728_v11.json \
  --precursor-manifest analysis/diagnostics/logs/stratolink2_retry_precursor_20260726_manifest.json \
  --handoff-power analysis/diagnostics/logs/stratolink2_soak_retry2_20260727_handoff.jsonl \
  --check-only

python3 analysis/diagnostics/flash_flight_candidate.py \
  --prefix analysis/diagnostics/logs/stratolink2_flight_flash_20260728_v11 \
  --summary analysis/diagnostics/logs/stratolink2_soak_retry2_20260727_final.json \
  --sensor-model analysis/diagnostics/logs/stratolink2_soak_retry2_20260727_sensor_model.json \
  --candidate-verification analysis/diagnostics/logs/stratolink2_flight_candidate_verification_20260728_v11.json \
  --precursor-manifest analysis/diagnostics/logs/stratolink2_retry_precursor_20260726_manifest.json \
  --handoff-power analysis/diagnostics/logs/stratolink2_soak_retry2_20260727_handoff.jsonl
```

The create-once wrapper refuses to run unless the final soak, sensor model,
candidate verification, precursor manifest, and their SHA-256 provenance all
still pass. It independently revalidates the fixed 256 KiB pre-retry flash
hash, the byte-identical post-soak dump, the IWDG-in-STOP option bit, every
preservation input (with only the growing standby log treated as an immutable
append-only prefix), and a current 4660 mV standby heartbeat with zero
reconnects. It selects J-Link serial `802007563`, invokes the generated
`loadfile`/`verifybin`/reset/run script, captures raw output, then reads
`0x0803F000-0x0803FFFF` and byte-compares it with the same pages in the
precursor flash dump. Any mismatch is a hard stop.

## 4. Cold-start/GNSS/region gate

The flight image has no bench region seed. If the retained session is legacy
or invalid, the board must remain RF-quiet until a genuinely fresh,
forward-moving GNSS epoch selects the legal region.

Require:

- no noncompliant blind US915 join before a fresh fix;
- two advancing iTOW epochs before any coordinates become valid;
- honest NOGPS telemetry state on every failed acquisition;
- clear-sky acquisition;
- bracket clear-sky, controlled no-fix, and reset-recovery acquisitions with
  PPK2. The strong application `yield()` must produce a shallow-WFI floor
  during the SparkFun explicit-poll and 100 ms retry waits while UART RX,
  SysTick, watchdog service, rail checks, and freefall preemption continue.
  Integrate the complete phases and compare their timing to the bounded source
  model; the model's active/control allowance remains conservative until this
  waveform exists;
- one forced frozen/silent receiver case that invokes the bounded inline PA0
  reset and then obtains a fresh fix inside the acquisition deadline;
- zero rejected-value PVTs: every accepted fresh epoch must also remain within
  the exact latitude, longitude, altitude, speed, heading, and satellite
  bounds before it can reach telemetry, regional selection, or B2B;
- at least one independent software-standby confirmation per completed
  acquisition cycle, with zero terminal standby failures: the firmware must
  receive a checksum-valid 10 Hz UBX-NAV-EOE marker, send the input-only
  UBX-RXM-PMREQ without pretending it has an ACK, and observe 350 ms of UART
  silence;
- after one confirmed standby, deliberately reset only the MAX-M10S while the
  MCU and its RAM remain powered, then enter a cycle below the 3,600 mV
  acquisition floor. `gps_ublox_note_power_skip()` intentionally resets the
  epoch anchor but currently retains the in-RAM standby-confirmed cache, so
  this fault injection must prove either that the shared exact-assembly rail
  makes a GNSS-only reset impossible without an MCU reset, or that measured
  GNSS current remains at standby after the skip. Any awake-current plateau
  hidden behind a cached successful return supersedes the new candidate and requires
  a source fix, new freeze, and repeated energy/HIL evidence;
- one forced standby-confirmation failure that advances the backup-failure and
  hardware-reset counters, followed by a later confirmation; if confirmation
  still fails after all retries, optional CTT/Meshtastic/B2B windows must remain
  suppressed and the next sleep must be capped at five seconds;
- repeat the failed-confirmation stimulus just below 4,400 mV with the flight
  supercap installed: the backup-failure counter must advance, the hardware-
  reset counter must not advance, auxiliary windows must remain suppressed,
  and PPK2/VSTOR evidence must show that the single bounded shutdown attempt
  does not cross the 3,600 mV acquisition floor or conservative 3,320 mV
  Flight-3 reported-plateau accounting floor; actual BOR remains a separate
  low-rail sweep;
- region lease word 29 begins at zero only after a fresh fix and advances by
  active time plus the conservative real-wall charge for planned RTC sleep;
  the STM32WLE5 29.5 kHz minimum LSI makes a nominal 1,200 s sleep charge
  exactly 1,302 s against STM32RTC's 32 kHz prescalers;
- on a FULL/solar cycle after one deliberately missed fix, begin from the
  measured worst-case-charged lease age near 1,302 s for a nominal 1,200 s
  STOP and bracket the complete shared LongFast
  window. Repeated private Meshtastic/B2B stimulus must be forwarded only until
  the exact `region_fix_remaining_tx_ms(live_age)` deadline (including its
  one-second guard), after which the radio must restore and remain TX-silent
  through the rest of the cadence. No later auxiliary or primary TX is allowed
  until a fresh advancing PVT renews the lease. Record live age, calculated
  budget, relay counters, and RF observation so a mere absence of traffic is
  not mistaken for deadline enforcement. Also set live age to the final
  represented second and require join, primary, and auxiliary TX to fail
  closed before any RF hand-off.

The low-rail sweep is a metrology test, not a pass/fail observation from TTN
alone. `low_rail_load_audit.py` binds the relevant component limits: BQ25570
maximum low-voltage high-side resistance is 2.9 ohm, MAX-M10S startup can reach
100 mA and its strapped 3.3 V V_IO mode requires at least 2.7 V, the base
RAK3172 requires 2.0 V, and the cold-cap ESR model is 90 milliohm. The
pessimistic ohmic screen leaves 3.301 V at the 3.600 V GPS floor—601 mV above
the GNSS V_IO minimum but 11 mV below the 3.312 V buck setpoint—and 2.868 V at
the 3.000 V / +14 dBm TX floor, 868 mV above the RAK3172 minimum. These are
plausibility margins only: TI's 93 mA guaranteed output-current point is for a
different 3.3-to-1.8 V condition, and short-pulse capacitance, wiring, cold,
and the fitted transient are not bounded by the arithmetic.

At 4.5, 4.4, 3.6, 3.5, 3.0, and below 3.0 V, simultaneously capture calibrated
PPK2 source VSTOR, board VOUT/VDDA, firmware VREFINT/raw/reported VSTOR, current,
reset cause, boot count, and success/failure of GNSS startup/standby, join,
primary TX, and auxiliary suppression. Fault-inject ADC initialization,
calibration, channel configuration, start, conversion-timeout, and invalid
VREFINT paths; each must report zero and fail load authorization closed. Require
no RF below 3.0 V, no GPS acquisition below 3.6 V, no resets during
authorized loads, and deterministic recovery when voltage rises. Repeat with
the final capacitor at room and cold, then set thresholds from the measured
worst case plus an explicit margin.

Bracket the initial clear-sky acquisition with a create-once
`cold-fail-closed` snapshot before it and a `joined-us` snapshot after it.
This is intentionally an asymmetric transition: requiring `joined-us` before
the first legal fix would contradict the fail-closed design. Replace `NN`
below with the exact next FCntUp reservation independently established from
the terminal TTN uplink plus the post-capture state:

```sh
python3 analysis/diagnostics/capture_flight_state.py \
  --label gps_cold_pre --profile cold-fail-closed
python3 analysis/diagnostics/capture_flight_state.py \
  --label gps_cold_post --profile joined-us
python3 analysis/diagnostics/compare_operational_states.py \
  --before analysis/diagnostics/logs/stratolink2_flight_state_gps_cold_pre_20260725.json \
  --before-manifest analysis/diagnostics/logs/stratolink2_flight_state_gps_cold_pre_20260725_manifest.json \
  --after analysis/diagnostics/logs/stratolink2_flight_state_gps_cold_post_20260725.json \
  --after-manifest analysis/diagnostics/logs/stratolink2_flight_state_gps_cold_post_20260725_manifest.json \
  --scenario gps-cold-start --expect-fcnt-up-after NN \
  --output analysis/diagnostics/logs/stratolink2_gps_cold_start_hil_20260725.json

python3 analysis/diagnostics/capture_flight_state.py \
  --label gps_recovery_pre --profile joined-us
# Deliberately force the documented frozen/silent GNSS condition here.
python3 analysis/diagnostics/capture_flight_state.py \
  --label gps_recovery_post --profile joined-us
python3 analysis/diagnostics/compare_operational_states.py \
  --before analysis/diagnostics/logs/stratolink2_flight_state_gps_recovery_pre_20260725.json \
  --before-manifest analysis/diagnostics/logs/stratolink2_flight_state_gps_recovery_pre_20260725_manifest.json \
  --after analysis/diagnostics/logs/stratolink2_flight_state_gps_recovery_post_20260725.json \
  --after-manifest analysis/diagnostics/logs/stratolink2_flight_state_gps_recovery_post_20260725_manifest.json \
  --scenario gps --expect-fcnt-up-advance 1 \
  --min-gps-hardware-resets 1 \
  --output analysis/diagnostics/logs/stratolink2_gps_recovery_hil_20260725.json
```

For the recovery interval, set the expected FCntUp advance to the exact
independently observed TTN transition. The cold-start comparison instead
requires the exact absolute post-join reservation because a new OTAA session
can legitimately replace any pre-fix retained counter. A passing comparison
rejects an MCU reboot, unauthorized pre-state, RAM/TAMP counter disagreement,
lost region authorization, implausible/stale post-fix coordinates, zero standby
confirmations, any terminal standby failure, and any new GNSS
begin/dynamic-model/backup/power/mission error.

The indoor window soak is not evidence for this gate.

If clear sky is temporarily unavailable, the remaining non-GNSS bench HIL may
continue on the exact flight image only after directly proving all three
fail-closed states through one atomic RAM+TAMP snapshot:

```sh
python3 analysis/diagnostics/capture_flight_state.py \
  --label cold_fail_closed --profile cold-fail-closed --check-only
python3 analysis/diagnostics/capture_flight_state.py \
  --label cold_fail_closed --profile cold-fail-closed
```

- `_joined` may be either zero or one;
- `REGION_ID` must be `0` (US915) at this US bench;
- `region_known` and `region_lease_trusted` must both be zero and no uplink may
  occur. Let one complete silent cycle finish, reset once more, and require
  both bits to remain zero with no newly valid TAMP lease; this is the physical
  two-boot regression for invalid-lease self-renewal.

After that proof, use the guarded allow-list wrapper to copy and execute the
exact candidate-bound authorization script. It may set only the RAM lease age,
authorization flag, and explicit trusted-provenance bit:

```sh
python3 analysis/diagnostics/apply_flight_hil_action.py \
  --action authorize-us --label bench \
  --before-state analysis/diagnostics/logs/stratolink2_flight_state_cold_fail_closed_20260725.json \
  --before-manifest analysis/diagnostics/logs/stratolink2_flight_state_cold_fail_closed_20260725_manifest.json \
  --check-only
python3 analysis/diagnostics/apply_flight_hil_action.py \
  --action authorize-us --label bench \
  --before-state analysis/diagnostics/logs/stratolink2_flight_state_cold_fail_closed_20260725.json \
  --before-manifest analysis/diagnostics/logs/stratolink2_flight_state_cold_fail_closed_20260725_manifest.json
# Wait for one observed OTAA join/primary uplink and the end-of-cycle lease save.
python3 analysis/diagnostics/capture_flight_state.py \
  --label bench_authorized --profile authorized-us
python3 analysis/diagnostics/compare_hil_action_states.py \
  --before analysis/diagnostics/logs/stratolink2_flight_state_cold_fail_closed_20260725.json \
  --before-manifest analysis/diagnostics/logs/stratolink2_flight_state_cold_fail_closed_20260725_manifest.json \
  --action-manifest analysis/diagnostics/logs/stratolink2_flight_action_authorize_us_bench_20260725_manifest.json \
  --after analysis/diagnostics/logs/stratolink2_flight_state_bench_authorized_20260725.json \
  --after-manifest analysis/diagnostics/logs/stratolink2_flight_state_bench_authorized_20260725_manifest.json \
  --scenario authorize-us \
  --output analysis/diagnostics/logs/stratolink2_bench_authorize_hil_20260725.json
```

The wrapper requires a fresh fail-closed state, the exact candidate and flash
manifests, a live 4660 mV PPK2 heartbeat, the known J-Link serial, and the
candidate report's byte hash for the generated script. The comparator requires
no reboot and proves that a valid RAM/TAMP lease appeared. This does not alter
the binary and is not GNSS evidence. Do not take the create-once after-state
until one observed loop has persisted the lease; the RAM-only action itself
does not write TAMP.

## 5. Join, uplink, and retained session

After a fresh US-region fix:

1. Bracket the first successful OTAA join with a PPK2 phase capture. Require
   join-request TX, the shallow-WFI pre-RX floor, the authenticated RX1 or RX2
   response, restored TX PHY, and one subsequent SF9/BW125 fPort-1 uplink.
   Separately, with the local gateway safely disabled or the RF path
   controllably attenuated, capture one deliberately empty attempt through
   RX2 close. Require the 4.750/5.750 s arm and 5.500/6.740 s close offsets,
   integrated energy, rail sag, and no second attempt inside the 15 s flight
   budget. Restore the gateway/RF path immediately and prove a successful
   rejoin. Do not alter credentials or bypass DevNonce journaling to create
   the empty case.
2. During a separate controlled attempt, stimulate LIS2DH12 INT1 in the
   pre-window wait and then an armed join window. Require prompt abort into
   the freefall mission, complete LoRaWAN TX-PHY restoration, and a later
   clean rejoin.
3. Capture the complete reserved journal and prove it followed the exact
   firmware transition once. The comparator simulates the real two-page
   algorithm byte-for-byte, including the inactive-page erase at rollover:

   ```sh
   python3 analysis/diagnostics/capture_devnonce_journal.py \
     --label postjoin --check-only
   python3 analysis/diagnostics/capture_devnonce_journal.py \
     --label postjoin
   python3 analysis/diagnostics/decode_devnonce_journal.py \
     --before \
     analysis/diagnostics/logs/stratolink2_flight_flash_20260725_reserved_after.bin \
     --before-manifest \
     analysis/diagnostics/logs/stratolink2_flight_flash_20260725_manifest.json \
     --after \
     analysis/diagnostics/logs/stratolink2_devnonce_postjoin_20260725.bin \
     --after-manifest \
     analysis/diagnostics/logs/stratolink2_devnonce_postjoin_20260725_manifest.json \
     --expect-advance 1 \
     --output \
     analysis/diagnostics/logs/stratolink2_devnonce_join_transition_20260725.json
   ```

   A corrupt record, duplicate/non-contiguous nonce history, extra byte
   mutation, wrong append value, wrong page choice, or unexpected erase is a
   hard stop.
4. Capture and decode health plus TAMP under one halt:

   ```sh
   python3 analysis/diagnostics/capture_flight_state.py \
     --label postjoin --profile joined-us
   ```

   The wrapper reads all 51 exact-ELF symbols and all 20 physical TAMP words under one
   halt, redacts retained session keys from the decoded JSON, checks v3/CRC,
   RAM-versus-TAMP FCnt and lease consistency, boot retention, US915 state,
   and radio failure accounting, and preserves the private raw read plus a
   redacted hash manifest.
5. Require next FCntUp already reserved beyond the transmitted frame and a
   valid fresh region lease.
6. Reset through J-Link without removing PPK2 power. Require boot count +1,
   session restore without a new join/DevNonce, and the next uplink to advance
   rather than replay the prior FCntUp. Capture both state and journal:

   ```sh
   python3 analysis/diagnostics/reset_flight_candidate.py \
     --label session --check-only
   python3 analysis/diagnostics/reset_flight_candidate.py \
     --label session
   python3 analysis/diagnostics/capture_flight_state.py \
     --label postreset --profile joined-us
   python3 analysis/diagnostics/capture_devnonce_journal.py \
     --label postreset
   python3 analysis/diagnostics/decode_devnonce_journal.py \
     --before \
     analysis/diagnostics/logs/stratolink2_devnonce_postjoin_20260725.bin \
     --before-manifest \
     analysis/diagnostics/logs/stratolink2_devnonce_postjoin_20260725_manifest.json \
     --after \
     analysis/diagnostics/logs/stratolink2_devnonce_postreset_20260725.bin \
     --after-manifest \
     analysis/diagnostics/logs/stratolink2_devnonce_postreset_20260725_manifest.json \
     --expect-advance 0 \
     --output \
     analysis/diagnostics/logs/stratolink2_devnonce_reset_transition_20260725.json
   python3 analysis/diagnostics/compare_flight_states.py \
     --before \
     analysis/diagnostics/logs/stratolink2_flight_state_postjoin_20260725.json \
     --before-manifest \
     analysis/diagnostics/logs/stratolink2_flight_state_postjoin_20260725_manifest.json \
     --reset-manifest \
     analysis/diagnostics/logs/stratolink2_flight_reset_session_20260725_manifest.json \
     --after \
     analysis/diagnostics/logs/stratolink2_flight_state_postreset_20260725.json \
     --after-manifest \
     analysis/diagnostics/logs/stratolink2_flight_state_postreset_20260725_manifest.json \
     --scenario session-reset \
     --expect-fcnt-up-advance 1 \
     --output \
     analysis/diagnostics/logs/stratolink2_session_reset_transition_20260725.json
   ```

   Increase `--expect-fcnt-up-advance` only if the TTN record proves that exact
   number of controlled post-reset uplinks.

## 6. Class-A downlink durability

The current compact stack authenticates downlink FOpts but does not execute or
answer MAC commands. During the precursor hold, TTN therefore logged an
unanswered `DevStatusReq` after every observed uplink while all three regional
device records inherited nonzero server defaults. The guarded remediation in
`logs/stratolink2_ttn_devstatus_remediation_20260727.json` explicitly set both
per-device status periodicities to zero for NA/EU/AS and read back the exact
disabled state without changing the flight binary. A subsequent read found one
already-sent `CID_DEV_STATUS` request pending on the active NA session and zero
pending requests on EU/AS. Before queueing an application command, require a
later NA primary uplink with no new `ns.mac.dev_status.request`; one terminal
`ns.mac.command.unanswered` is expected while the old request is retired. Then
require a read-only pending-request inventory of zero and a following uplink
with neither event. Do not infer from that server-side check that arbitrary
FOpts are implemented. Re-enable status requests only after a future image
implements and qualifies `DevStatusAns`.

This gate closed on the precursor at
`2026-07-27T08:39:34.223341220Z`. The following uplink reached Network Server
receive/process, Application Server receive/forward, and Storage with no
unanswered/request/downlink event; NA/EU/AS pending counts were all zero. The
passing create-once record is
`logs/stratolink2_ttn_devstatus_postchange_phase2b_20260727.json`. Preserve the
earlier `phase2` record as a failed watcher-specification artifact: it required
the redundant, non-stable `ns.up.data.forward` audit event even though the
downstream Application Server and Storage events prove forwarding. This closes
only periodic DevStatus scheduling, not application-command HIL.

1. Before queueing a command, capture one empty Class-A exchange with the PPK2
   from primary-TX end through RX2 close at both a representative FULL rail and
   a representative REDUCED rail. Require RX1/RX2 arm offsets near 4.750/5.750 s,
   close offsets near 5.500/6.740 s, a low-current 4.75 s pre-RX1 WFI floor,
   both RX plateaus, continuous watchdog progress, and LoRaWAN-TX PHY restoration.
   Record current and integrated energy rather than substituting the
   `class_a_energy_audit.py` typical-current screen. With a safely controlled
   LIS2DH12 INT1 stimulus during each phase, require the optional wait/window to
   abort promptly into the freefall mission without waiting for RX2 close.
   Repeat with the final fitted supercapacitor and preserve the phase trace plus
   rail-sag evidence.
2. Choose a new modulo-256 sequence 1–127 steps ahead of the captured retained
   value. Inspect the empty TTN queue first (default dry-run), then explicitly
   queue one harmless fPort-10 PING:

   ```sh
   analysis/.venv/bin/python analysis/diagnostics/ttn_downlink_test.py \
     --seq NN
   analysis/.venv/bin/python analysis/diagnostics/ttn_downlink_test.py \
     --seq NN --queue \
     --output analysis/diagnostics/logs/stratolink2_downlink_initial_queue_20260725.json
   ```
3. Require RX1 or RX2 IRQ, valid MIC/decrypt, exact application length, and
   command count +1.
   Before closing this gate, use a separate controllable LoRa transmitter (the
   RTL-SDR is receive-only) to send one wrong-address or bad-MIC frame on the
   exact RX1 PHY shortly after the window opens. Include an oversized but
   CRC-valid candidate and prove it is rejected as a complete frame rather
   than authenticated as a truncated prefix. First require a later valid
   TTN RX1 PING in that same absolute window to succeed, proving invalid RF
   re-arms rather than preempts RX1. Then repeat with no valid RX1 and force the
   legitimate PING into RX2; require two logical windows armed, the final
   accepted window to be RX2, FCntDown +1 exactly once, and command count +1
   exactly once. Repeat the same early-RX1/RX2 pattern during one controlled
   OTAA rejoin. The injected frame must contain no valid project key or command.
4. Capture `--label downlink_prereset --profile joined-us`; require TAMP next
   FCntDown to equal RAM next FCntDown, TAMP word 25 to contain a valid v2
   command-state record with the accepted sequence and actual relay policy,
   and zero sequence-persist failures. Require the following successful
   40-byte primary to report the same command ACK sequence and relay state:

   ```sh
   python3 analysis/diagnostics/capture_flight_state.py \
     --label downlink_prereset --profile joined-us
   ```
5. Reset, capture `--label downlink_postreset --profile joined-us`, and require
   the same next FCntDown to restore:

   ```sh
   python3 analysis/diagnostics/reset_flight_candidate.py \
     --label downlink --check-only
   python3 analysis/diagnostics/reset_flight_candidate.py \
     --label downlink
   python3 analysis/diagnostics/capture_flight_state.py \
     --label downlink_postreset --profile joined-us
   python3 analysis/diagnostics/compare_flight_states.py \
     --before \
     analysis/diagnostics/logs/stratolink2_flight_state_downlink_prereset_20260725.json \
     --before-manifest \
     analysis/diagnostics/logs/stratolink2_flight_state_downlink_prereset_20260725_manifest.json \
     --reset-manifest \
     analysis/diagnostics/logs/stratolink2_flight_reset_downlink_20260725_manifest.json \
     --after \
     analysis/diagnostics/logs/stratolink2_flight_state_downlink_postreset_20260725.json \
     --after-manifest \
     analysis/diagnostics/logs/stratolink2_flight_state_downlink_postreset_20260725_manifest.json \
     --scenario downlink-reset \
     --output \
     analysis/diagnostics/logs/stratolink2_downlink_reset_transition_20260725.json
   ```

   Capture the post-reset state before another uplink; the comparator therefore
   requires FCntUp unchanged, FCntDown retained, boot +1, volatile command
   counters cleared, and the same retained application sequence plus relay
   state restored into RAM. The first post-reset 40-byte primary must report a
   reset cause consistent with the controlled reset and the same ACK/state.
6. Queue a new LoRaWAN downlink carrying the *same application sequence*.
   Require a valid new FCntDown/MIC receive but no command-count increment and
   no state change. Capture it as `downlink_replay_post`, then machine-check the
   exact one-frame transition (replace `NN` with the retained sequence):

   ```sh
   analysis/.venv/bin/python analysis/diagnostics/ttn_downlink_test.py \
     --seq NN --queue \
     --output analysis/diagnostics/logs/stratolink2_downlink_replay_queue_20260725.json
   # Wait for the controlled primary uplink/downlink, then:
   analysis/.venv/bin/python analysis/diagnostics/capture_flight_state.py \
     --label downlink_replay_post --profile joined-us
   analysis/.venv/bin/python analysis/diagnostics/compare_operational_states.py \
     --before analysis/diagnostics/logs/stratolink2_flight_state_downlink_postreset_20260725.json \
     --before-manifest analysis/diagnostics/logs/stratolink2_flight_state_downlink_postreset_20260725_manifest.json \
     --after analysis/diagnostics/logs/stratolink2_flight_state_downlink_replay_post_20260725.json \
     --after-manifest analysis/diagnostics/logs/stratolink2_flight_state_downlink_replay_post_20260725_manifest.json \
     --scenario downlink-replay --expect-fcnt-up-advance 1 \
     --expect-command-sequence-after NN \
     --output analysis/diagnostics/logs/stratolink2_downlink_replay_20260725.json
   ```

   Queue the next monotonically valid sequence, capture it as
   `downlink_accept_post`, and require exactly one application:

   ```sh
   analysis/.venv/bin/python analysis/diagnostics/ttn_downlink_test.py \
     --seq NEXT --queue \
     --output analysis/diagnostics/logs/stratolink2_downlink_accept_queue_20260725.json
   # Wait for the next controlled primary uplink/downlink, then:
   analysis/.venv/bin/python analysis/diagnostics/capture_flight_state.py \
     --label downlink_accept_post --profile joined-us
   analysis/.venv/bin/python analysis/diagnostics/compare_operational_states.py \
     --before analysis/diagnostics/logs/stratolink2_flight_state_downlink_replay_post_20260725.json \
     --before-manifest analysis/diagnostics/logs/stratolink2_flight_state_downlink_replay_post_20260725_manifest.json \
     --after analysis/diagnostics/logs/stratolink2_flight_state_downlink_accept_post_20260725.json \
     --after-manifest analysis/diagnostics/logs/stratolink2_flight_state_downlink_accept_post_20260725_manifest.json \
     --scenario downlink-accept --expect-fcnt-up-advance 1 \
     --expect-command-sequence-after NEXT \
     --output analysis/diagnostics/logs/stratolink2_downlink_accept_20260725.json
   ```

   `downlink-replay` requires FCntDown +1, one clean RX1/RX2 IRQ/frame,
   command-parser RX +1, application count +0, and identical RAM/TAMP
   sequence. `downlink-accept` requires the next FCntDown, a monotonically newer
   sequence, application count +1, exact PING shape, and RAM/TAMP agreement.
   This proves the retained application-sequence replay boundary used by B2B
   commands, in addition to LoRaWAN frame-counter replay protection. It does
   not prove transport-frame freshness: the wire-v3 receive dedup cache is
   RAM-only, expires after 240 minutes, and clears on reset, so exact
   authenticated-frame replay remains a fleet-deployment blocker.
7. Delivery remains at-most-once: a reset after durable reservation but before
   dispatch can lose an effect, so retry with a newer application sequence.
   Telemetry v2 closes the normal loop on the next successful primary, but is
   not a same-downlink commit-confirm protocol.
8. With successively newer sequences, use `ttn_downlink_test.py --relay off`
   and then `--relay on` (dry-run first, `--queue` only after confirming the
   queue is empty). For each command require RX1/RX2 acceptance, TAMP/RAM state
   agreement, and the next 40-byte primary's ACK sequence plus relay bit.
   While off, repeat the public Meshtastic stimulus and require no public
   forward; prove B2B command/ACK service remains enabled. Restore relay-on,
   verify a public forward, and leave the final retained state enabled.

## 7. B2B retained origin ID

Queue a harmless broadcast PING so the authenticated B2B carrier originates a
frame without needing a second balloon. Require:

- TAMP word 26 has tag `0xB2B2`, a value byte, and its complement;
- the retained value is the successor of the queued frame's ID;
- reset restores the successor rather than zero;
- the next originated frame consumes a different ID.

Use create-once `b2b_prereset` and `b2b_postreset` joined-US snapshots rather
than reading word 26 separately, then compare the evidence-bound decoded
captures:

```sh
python3 analysis/diagnostics/capture_flight_state.py \
  --label b2b_prereset --profile joined-us
python3 analysis/diagnostics/reset_flight_candidate.py \
  --label b2b --check-only
python3 analysis/diagnostics/reset_flight_candidate.py \
  --label b2b
python3 analysis/diagnostics/capture_flight_state.py \
  --label b2b_postreset --profile joined-us
python3 analysis/diagnostics/compare_flight_states.py \
  --before \
  analysis/diagnostics/logs/stratolink2_flight_state_b2b_prereset_20260725.json \
  --before-manifest \
  analysis/diagnostics/logs/stratolink2_flight_state_b2b_prereset_20260725_manifest.json \
  --reset-manifest \
  analysis/diagnostics/logs/stratolink2_flight_reset_b2b_20260725_manifest.json \
  --after \
  analysis/diagnostics/logs/stratolink2_flight_state_b2b_postreset_20260725.json \
  --after-manifest \
  analysis/diagnostics/logs/stratolink2_flight_state_b2b_postreset_20260725_manifest.json \
  --scenario b2b-reset \
  --output \
  analysis/diagnostics/logs/stratolink2_b2b_reset_transition_20260725.json
```

A second physical StratoLink radio is still required to prove over-air
store-and-forward, authentication, TTL decrement, dedup, ACK return, and the
public-relay-off/B2B-still-on policy boundary.

## 8. Sensors, freefall, CTT, relay, and power

On the exact flight image:

- compare TMP117/MS5611/LTR390/LIS2DH12 readings against the bench references;
- use a current-limited/series-resistor I2C fault fixture to hold SDA low for
  longer than the framework's 100 ms transfer timeout during one sensor phase,
  then release it. Prove the mission does not hang or reboot, the one bounded
  all-sensors-failed bus recovery counter `s_sensor_i2c_bus_recoveries`
  advances exactly once, all four I2C sensors produce plausible
  values on the retry or following cycle, and TTN frame counters remain
  contiguous. Do not hard-short a live pin directly with a probe;
- separately interrupt an LTR390 transaction after optical enable and keep the
  fault present. Capture the exact-ELF state after each fast wake: require
  `s_optical_quiet_retries` to advance 1, 2, 3, 4, 5 without wrap, no optical
  read or auxiliary RF while faulted, and then a normal-cadence primary GPS/TTN
  cycle while the counter remains saturated at 5. Release the fault and require
  confirmed standby, the fault flag and retry counter to clear, and optical
  sampling to resume. PPK2-measure the faulted intervals; source logic does not
  make a permanently active 200 uA sensor energetically acceptable;
- bracket an intentionally quiet capture, a controlled audible stimulus, panel-
  cover handling, and active-solar harvester noise with exact-ELF acoustic
  diagnostics and decoded telemetry; require attempts=captures+failures,
  unavailable on a deliberately failed/skipped capture rather than quiet,
  zero quiet/harvester events on successful captures, a stimulus event, and a
  plausible variance-to-adaptive-floor separation;
- require the exact-ELF TMP117 direct-read counter to advance, with the
  fallback and rejected-power-on-sentinel counters identifying any substitution;
- induce controlled freefall and prove active-cycle preemption, rapid cadence,
  exit/cooldown, chatter suppression, and later genuine-low-g re-arm;
- in daylight above the relay solar threshold, prove real Meshtastic receive,
  delayed forward, competing-duplicate cancellation, dedup-after-success,
  hop-zero/directed-next-hop drop,
  CAD-busy retry, anonymous `next_hop=relay_node=0` header behavior, and
  LoRaWAN PHY restoration; require the appended relay queue/CAD/error counters
  to match the induced cases, a subsequent TTN uplink, and either all-zero
  `s_radio_diag` or a fully accounted restore attempt/recovery pair;
- bracket that controlled LongFast window with a PPK2 phase capture. Require
  continuous radio RX over a shallow-WFI MCU floor rather than the former
  active-MCU plateau, visible one-hertz housekeeping without missed watchdog
  service, prompt VSTOR/solar/freefall exits, and the return to STOP1. Integrate
  the complete window current; `auxiliary_rx_energy_audit.py` deliberately
  reports the 5.5 mA radio-only value as a lower screen, not measured total.
  Repeat with the fitted final supercapacitor and preserve rail-sag evidence;
- with a second provisioned StratoLink node, prove wire-v3 authenticated crumb,
  command, ACK, TTL-forward, wrong-key rejection, randomized contention, and
  CAD-busy/refund behavior; also drop an ACK, replay the exact authenticated
  command after dedup reset/expiry, and prove it is re-ACKed without reapplying
  the command; then deliver opcode `0x02` with argument `0`, prove ordinary
  Meshtastic frames are no longer queued or forwarded while authenticated B2B
  command/ACK traffic still crosses the same LongFast window, and re-enable
  the public relay with a newer command sequence;
- CTT is additionally blocked by the fitted high-band RAK3172: RAK assigns
  434 MHz to the separate low-band module. With a real compatible tag, first
  prove usable receive margin through the exact module and antenna, then prove
  decode, queue, fPort-11 uplink, and database insert. The StratoLink-2 flight
  default is now `CTT_LISTEN_ENABLE=false`; keep it disabled through the
  immutable freeze unless that complete gate closes, then repeat all builds
  and verifiers before re-enabling it. Do not spend a 60-second flight window
  on an unsupported receiver claim;
- EU868 is also an exact-SKU gate: BOM `C18548052` is
  `RAK3172-9-SM-NI`, which RAK lists for 9xx MHz regions, while EU868 is
  assigned to `RAK3172-8-SM-NI`. The 142 historical EU packets prove one
  assembly operated at 868 MHz but do not qualify conducted TX power/RX
  sensitivity, antenna match, certification, cold margin, or repeatability.
  Obtain manufacturer confirmation or run those measurements plus a real EU
  join/uplink/downlink at launch-relevant margin; the local US gateway and an
  RTL-SDR amplitude comparison cannot close the full gate;
- do not take the presently shaded board directly into unrestricted full sun
  after fitting the flight supercap. `supercap_charge_ceiling_audit.py` binds
  the 8.25 MΩ / 4.22 MΩ, ±1% production divider to a 5.363282 V nominal
  ceiling. TI conditions its datasheet ±2% overall threshold guarantee on
  ±0.1% resistors, but its BQ25570EVM guide explicitly publishes min/max
  thresholds using ±2% set-point accuracy plus ±1% resistor tolerance. The
  conservative TI-method ±1%-ratio plus threshold screen is 5.543664 V
  at the resistor reference temperature; adding their ±100 ppm/°C TCR over
  the BQ25570 operating range raises the screen to 5.591979 V. Both are above
  the 5.5 V absolute maximum shared by BQ25570 and C5. Flight 3 peaked
  at 5.412 V, which is useful operation evidence but only 88 mV of observed
  margin and not a production guarantee. First lower/qualify the divider or
  use a current-limited controlled-light ramp with calibrated independent
  VBAT/VSTOR transient capture and an abort below 5.5 V. Only after that gate
  is closed, measure maximum-light/temperature charge, darkness decay, sleep
  current, GPS/TX sag, tier crossings, post-load suppression, and recovery.
  The exact capacitor is specified at 0.8-1.2 F and 50 mOhm maximum ESR at
  1 kHz, not exactly 1 F. `supercap_night_reserve_audit.py` therefore screens
  the minimum 0.8 F part. With no GPS, sensors, TX/RX, watchdog wake overhead,
  cold, aging, or sag charged to the budget, the current nominal ceiling gives
  only 13.759 h at 33 uA with zero capacitor leakage, or 11.075 h when the
  measured 35 uA sleep value is combined with the datasheet 6 uA leakage
  limit at 5.5 V/23 °C/120 h. The earlier Vishay `CRCW04027M50FKED`
  (7.50 MOhm, 0402, ±1%, ±100 ppm/K) is retained only as the detailed-balancer
  comparison reference. Its full modeled upper bound is 5.251917 V. CAP-XX
  says its dual cells are capacitance-matched within ±4%; the resulting worst
  initial-cell screen is 2.730997 V, only 19.003 mV below the 2.75 V cell
  rating. The 7.50 MOhm minimum-cap baseline is 11.587 h at 33 uA/no leakage
  and 9.326 h at 35+6 uA before balancer overhead. The current safer-margin
  prototype candidate is 7.32 MOhm: exact 0402/1%/100 ppm/K options include
  Vishay `CRCW04027M32FKED` and Yageo `RC0402FR-077M32L`. It screens to
  5.170302 V total and 2.688557 V on the worst initial cell, gaining 42.440 mV
  of cell headroom over 7.50 MOhm while reducing the same 35+6 uA baseline to
  8.907 h. A 7.15 MOhm ratio would provide 101.525 mV of cell headroom and an
  8.510 h baseline. The former 7.68 MOhm candidate fails the cell-level screen
  at 2.773436 V. None is approved until CAP-XX reviews the choice and the
  delivered part and exact reworked assembly are measured.
  `flight3_darkness_audit.py` independently binds all 37 accepted GPS
  waypoints to the 320-point cached mean reconstruction and computes the
  altitude-dependent direct-sun horizon once per minute. The longest complete
  clear-sky geometric night is 9.674 h. The unsafe current divider's simple
  baseline exceeds it by only 1.401 h before any active work; the 7.50 MOhm
  reference is already 0.348 h short and the 7.32 MOhm safer-margin candidate
  is 0.767 h short. Clouds, panel attitude, cold, active cycles, conversion,
  aging, and sag can only increase the electrical-darkness requirement. These
  are warning screens, not endurance predictions; fit-and-measure darkness HIL
  on the exact frozen image must cover at least 9.674 h plus an explicit
  cloud/attitude reserve before launch;
- `launch_darkness_envelope_audit.py` prospectively bounds the planned Friday
  2026-07-31 launch at the highest accepted Flight-3 latitude and altitude. It
  finds an 8.667 h clear-sky launch night, a 10.091 h maximum within 30 days,
  and 13.252 h within 90 days. The 7.32 MOhm minimum-cap baseline has only
  0.240 h launch-night margin and is first exceeded on 2026-08-07; 7.50 MOhm
  has 0.659 h and is first exceeded on 2026-08-16. Even the voltage-unsafe
  8.25 MOhm divider is exceeded on 2026-09-17. This stationary geometric
  envelope is not a trajectory or endurance prediction; excluding active
  work, cloud, attitude, conversion, cold, aging, and sag makes every margin
  optimistic. A long-duration circumnavigation therefore cannot be cleared by
  a divider-only substitution;
- `mission_energy_store_sizing_audit.py` closes the largest optimistic gap in
  the preceding baseline-only comparisons by charging each voltage-eligible
  cycle for the existing typical 2 s hot-GNSS model, exact 40-byte SF9 primary
  airtime, and mandatory empty Class-A radio receive. It preserves the source
  tier transitions: 20-minute FULL cadence, 30-minute lower cadence, GPS
  suppression below 3.6 V, and Class-A suppression below 3.5 V. It also adds
  the unqualified TLV8801 balancer's screened overhead. At the full tolerance-
  lower charge corner, the 0.8 F minimum part reaches the conservative 3.32 V
  accounting floor after only 3.509 h with 7.32 MOhm and 3.798 h with 7.50
  MOhm. Even the specified 1.2 F maximum reaches only 5.806/5.950 h, so the
  entire 0.8-1.2 F part range fails the 8.667 h launch night. This lower
  engineering screen requires 1.822/1.779 F for launch
  night, 2.103/2.036 F for the first 30 days, and 2.764/2.662 F for 90 days.
  Those are minimum sizing bounds, not recommendations: sensors, WFI MCU
  current, joins, failures, cold, aging, weather, sag, reserve, and actual BOR
  remain omitted;
- perform any R1 rework and board cleaning before installing C5. TI warns that
  residual flux in parallel with 1-20 MOhm programming resistors can materially
  shift the threshold and recommends cleaning after removal and again after
  installation. Record microscope images, independently measure R1/R2 with an
  appropriate high-impedance method, and prove no residue remains around U1,
  R1, and R2. Then install the fully discharged, correctly polarized C5 as a
  separate manual operation: CAP-XX forbids infrared/hot-air reflow and wave
  soldering, specifies a 350 ±10 °C iron for 3-4 seconds per terminal with no
  more than three passes, and says to consult it before washing an installed
  device. Never wash the fitted capacitor as part of the divider-cleaning step;
- C5 is a dual-cell, three-terminal device and the current PCB leaves pad 3,
  its balance terminal, unconnected. CAP-XX says it does not add internal
  balancing and highly recommends balancing for every series-connected module.
  Obtain its application-specific guidance, add a low-leakage active network
  using the midpoint, and update the power budget. CAP-XX AN1002 normally
  recommends 10 kOhm per-cell passive resistors, which would add 252.036 uA at
  the 7.50 MOhm comparison-reference ceiling and collapse that baseline to
  1.305 h. Its
  viable low-current reference instead uses `TLV8801DBVT` with two
  `MCA1206MD1005BP100` 10 MOhm / 0.1% / 25 ppm/K reference resistors and
  22 Ohm midpoint protection. The modeled divider plus CAP-XX typical op-amp
  overhead is 0.732 uA, lowering the 7.50 MOhm reference baseline from 9.326 h to
  9.163 h before active cycles. TI's 700 nA maximum op-amp current produces a
  0.952 uA screening overhead and 9.115 h baseline. Divider tolerance/TCR plus
  4.5 mV maximum offset leaves 112.648 mV steady balanced-cell margin, but the
  initial 4% mismatch asks for 4.774 mA at the full ceiling while TI specifies
  only a typical 4.7 mA short-circuit current. Implement a reviewed
  daughterboard/flex—not an unreviewed flight dead-bug—and HIL-prove startup,
  saturation, correction time, and RF stability. Manufacturer data on a
  different capacitor reports about 4 uA total after 28 h and 1.5 uA after a week.
  Also evaluate the purpose-built dual `ALD910025SALI` SAB MOSFET. It removes
  the divider/op-amp; the source-bound typical model gives 114.683 uA net
  initial equalization and 9.298 h modeled 25 C darkness runtime. Its current
  curve and temperature coefficients are typical-only, however, and the
  industrial part stops at -40 C. The model therefore ranks architectures; it
  cannot qualify one. Obtain CAP-XX review and exact-part cold/current data or
  close those uncertainties entirely with bounded HIL.
  The candidate comparison and acceptance sequence are fixed in
  `STRATOLINK2_SUPERCAP_BALANCER_DECISION_20260725.md`.
  Measure both cell voltages independently during charge, darkness,
  load, recovery, and temperature HIL; total VSTOR alone cannot close this gate;
- cold-soak the exact final assembly and supercap through at least the
  Flight-3-observed -42.1 °C reported-board envelope. The fitted non-TCXO
  RAK3172 is rated only to -20 °C; MAX-M10S, MS5611, LTR390, LIS2DH12,
  BQ25570, T3902, and the planned Murata DMF supercap stop at -40 °C. Only the
  TMP117 among the nine screened critical active/storage parts covers the
  envelope. The three <=-40 °C flight packets reported only 3.322-3.374 V
  VSTOR, and the coldest row was 2 mV above the 3.320 V reported plateau.
  The flown fixed-VDDA ADC lost actual-VSTOR observability in buck dropout, so
  this is not a measured brownout threshold; treat it as correlation requiring
  direct power HIL, not a causal conclusion. Component temperatures may differ
  from the board reading,
  so measure them while requiring continuous telemetry, a forced cold rejoin,
  command receive, fresh-GNSS behavior, sensor diagnostic coherence, PHY
  restoration, and cold capacitance/ESR sag rather than treating the earlier
  flight's isolated cold packets as a qualification certificate.

Use separate create-once `joined-us` snapshots around each controlled
operational stimulus. The redacted decoder now preserves the TMP117
direct/fallback/sentinel counters as well as the relay/CTT/radio counters.
Compare the exact evidence-bound artifacts rather than transcribing debugger
values:

Before acoustic stimulus, microscope or backlight the exact MK1 underside PCB
port and preserve a photo showing that the 0.500 mm bore is free of solder,
flux, tape, coating, and debris. `microphone_port_audit.py` proves only that the
embedded design geometry follows TDK's nominal pattern; the bore is exactly at
the manufacturer's lower recommended limit, and the surviving historical
mask-aperture/GND-track DRC finding prevents substituting CAD intent for this
physical check. Do not touch the active shaded soak to perform it.

```sh
python3 analysis/diagnostics/capture_flight_state.py \
  --label tmp117_pre --profile joined-us
# Wait for exactly one completed sensor/primary-uplink cycle.
python3 analysis/diagnostics/capture_flight_state.py \
  --label tmp117_post --profile joined-us
python3 analysis/diagnostics/compare_operational_states.py \
  --before analysis/diagnostics/logs/stratolink2_flight_state_tmp117_pre_20260725.json \
  --before-manifest analysis/diagnostics/logs/stratolink2_flight_state_tmp117_pre_20260725_manifest.json \
  --after analysis/diagnostics/logs/stratolink2_flight_state_tmp117_post_20260725.json \
  --after-manifest analysis/diagnostics/logs/stratolink2_flight_state_tmp117_post_20260725_manifest.json \
  --scenario tmp117 --expect-fcnt-up-advance 1 \
  --output analysis/diagnostics/logs/stratolink2_tmp117_hil_20260725.json

python3 analysis/diagnostics/capture_flight_state.py \
  --label acoustic_quiet_pre --profile joined-us
# Keep the room quiet through exactly one sensor/uplink cycle. Repeat this
# quiet gate separately during panel-cover handling and active solar charging.
python3 analysis/diagnostics/capture_flight_state.py \
  --label acoustic_quiet_post --profile joined-us
python3 analysis/diagnostics/compare_operational_states.py \
  --before analysis/diagnostics/logs/stratolink2_flight_state_acoustic_quiet_pre_20260725.json \
  --before-manifest analysis/diagnostics/logs/stratolink2_flight_state_acoustic_quiet_pre_20260725_manifest.json \
  --after analysis/diagnostics/logs/stratolink2_flight_state_acoustic_quiet_post_20260725.json \
  --after-manifest analysis/diagnostics/logs/stratolink2_flight_state_acoustic_quiet_post_20260725_manifest.json \
  --scenario acoustic-quiet --expect-fcnt-up-advance 1 \
  --output analysis/diagnostics/logs/stratolink2_acoustic_quiet_hil_20260725.json

python3 analysis/diagnostics/capture_flight_state.py \
  --label acoustic_stimulus_pre --profile joined-us
# Apply a repeatable periodic audible stimulus throughout the next cycle so it
# necessarily overlaps the 55 ms production capture.
python3 analysis/diagnostics/capture_flight_state.py \
  --label acoustic_stimulus_post --profile joined-us
python3 analysis/diagnostics/compare_operational_states.py \
  --before analysis/diagnostics/logs/stratolink2_flight_state_acoustic_stimulus_pre_20260725.json \
  --before-manifest analysis/diagnostics/logs/stratolink2_flight_state_acoustic_stimulus_pre_20260725_manifest.json \
  --after analysis/diagnostics/logs/stratolink2_flight_state_acoustic_stimulus_post_20260725.json \
  --after-manifest analysis/diagnostics/logs/stratolink2_flight_state_acoustic_stimulus_post_20260725_manifest.json \
  --scenario acoustic-stimulus --expect-fcnt-up-advance 1 \
  --output analysis/diagnostics/logs/stratolink2_acoustic_stimulus_hil_20260725.json

python3 analysis/diagnostics/capture_flight_state.py \
  --label freefall_short_pre --profile joined-us
# Apply one genuine short-drop stimulus. Require the prompt burst uplink in TTN.
python3 analysis/diagnostics/capture_flight_state.py \
  --label freefall_short_post --profile joined-us
python3 analysis/diagnostics/compare_operational_states.py \
  --before analysis/diagnostics/logs/stratolink2_flight_state_freefall_short_pre_20260725.json \
  --before-manifest analysis/diagnostics/logs/stratolink2_flight_state_freefall_short_pre_20260725_manifest.json \
  --after analysis/diagnostics/logs/stratolink2_flight_state_freefall_short_post_20260725.json \
  --after-manifest analysis/diagnostics/logs/stratolink2_flight_state_freefall_short_post_20260725_manifest.json \
  --scenario freefall-short --expect-fcnt-up-advance 1 \
  --output analysis/diagnostics/logs/stratolink2_freefall_short_hil_20260725.json

# After relay_pre exists and daylight/command gates prove the relay window is
# active, validate the local node without RF, then explicitly transmit an
# opaque PRIVATE_APP packet and exact-ID repeats. No text, payload, PSK,
# position, owner, or stable node ID is written to the evidence log.
python3 analysis/diagnostics/capture_flight_state.py \
  --label relay_pre --profile joined-us
analysis/.venv/bin/python analysis/diagnostics/meshtastic_hil_stimulus.py \
  --output analysis/diagnostics/logs/stratolink2_meshtastic_stimulus_check_20260725.jsonl
analysis/.venv/bin/python analysis/diagnostics/meshtastic_hil_stimulus.py \
  --transmit --repeats 1 --interval-seconds 0.8 --hop-limit 3 \
  --observe-seconds 180 \
  --output analysis/diagnostics/logs/stratolink2_meshtastic_stimulus_tx_20260725.jsonl
analysis/.venv/bin/python analysis/diagnostics/meshtastic_hil_stimulus.py \
  --transmit --repeats 10 --interval-seconds 0.1 --hop-limit 3 \
  --observe-seconds 60 \
  --output analysis/diagnostics/logs/stratolink2_meshtastic_stimulus_cancel_20260725.jsonl
analysis/.venv/bin/python analysis/diagnostics/meshtastic_hil_stimulus.py \
  --transmit --repeats 1 --hop-limit 0 --observe-seconds 60 \
  --output analysis/diagnostics/logs/stratolink2_meshtastic_stimulus_hop0_20260725.jsonl
analysis/.venv/bin/python analysis/diagnostics/meshtastic_hil_stimulus.py \
  --transmit --repeats 1 --hop-limit 3 --directed-next-hop \
  --observe-seconds 60 \
  --output analysis/diagnostics/logs/stratolink2_meshtastic_stimulus_directed_20260725.jsonl

# Each successful stimulus creates OUTPUT.manifest.json. Bind the five logs to
# their exact requested parameters. Require a genuine relay echo only from the
# single-packet positive case, and require no forwarded echo from the rapid
# exact-ID cancellation case; the target counter below supplies the positive
# proof that the latter absence was a real cancellation rather than RF loss.
analysis/.venv/bin/python analysis/diagnostics/validate_meshtastic_hil.py \
  --log analysis/diagnostics/logs/stratolink2_meshtastic_stimulus_check_20260725.jsonl \
  --manifest analysis/diagnostics/logs/stratolink2_meshtastic_stimulus_check_20260725.jsonl.manifest.json \
  --profile check --repeats 2 --hop-limit 3 --observe-seconds 0 \
  --output analysis/diagnostics/logs/stratolink2_meshtastic_stimulus_check_validated_20260725.json
analysis/.venv/bin/python analysis/diagnostics/validate_meshtastic_hil.py \
  --log analysis/diagnostics/logs/stratolink2_meshtastic_stimulus_tx_20260725.jsonl \
  --manifest analysis/diagnostics/logs/stratolink2_meshtastic_stimulus_tx_20260725.jsonl.manifest.json \
  --profile relay --repeats 1 --hop-limit 3 --observe-seconds 180 --min-echoes 1 \
  --output analysis/diagnostics/logs/stratolink2_meshtastic_stimulus_tx_validated_20260725.json
analysis/.venv/bin/python analysis/diagnostics/validate_meshtastic_hil.py \
  --log analysis/diagnostics/logs/stratolink2_meshtastic_stimulus_cancel_20260725.jsonl \
  --manifest analysis/diagnostics/logs/stratolink2_meshtastic_stimulus_cancel_20260725.jsonl.manifest.json \
  --profile cancel --repeats 10 --interval-seconds 0.1 --hop-limit 3 --observe-seconds 60 \
  --output analysis/diagnostics/logs/stratolink2_meshtastic_stimulus_cancel_validated_20260725.json
analysis/.venv/bin/python analysis/diagnostics/validate_meshtastic_hil.py \
  --log analysis/diagnostics/logs/stratolink2_meshtastic_stimulus_hop0_20260725.jsonl \
  --manifest analysis/diagnostics/logs/stratolink2_meshtastic_stimulus_hop0_20260725.jsonl.manifest.json \
  --profile hop-zero --repeats 1 --hop-limit 0 --observe-seconds 60 \
  --output analysis/diagnostics/logs/stratolink2_meshtastic_stimulus_hop0_validated_20260725.json
analysis/.venv/bin/python analysis/diagnostics/validate_meshtastic_hil.py \
  --log analysis/diagnostics/logs/stratolink2_meshtastic_stimulus_directed_20260725.jsonl \
  --manifest analysis/diagnostics/logs/stratolink2_meshtastic_stimulus_directed_20260725.jsonl.manifest.json \
  --profile directed --repeats 1 --hop-limit 3 --observe-seconds 60 \
  --output analysis/diagnostics/logs/stratolink2_meshtastic_stimulus_directed_validated_20260725.json

# Wait for the first subsequent primary TTN uplink after the relay window.
python3 analysis/diagnostics/capture_flight_state.py \
  --label relay_post --profile joined-us
python3 analysis/diagnostics/compare_operational_states.py \
  --before analysis/diagnostics/logs/stratolink2_flight_state_relay_pre_20260725.json \
  --before-manifest analysis/diagnostics/logs/stratolink2_flight_state_relay_pre_20260725_manifest.json \
  --after analysis/diagnostics/logs/stratolink2_flight_state_relay_post_20260725.json \
  --after-manifest analysis/diagnostics/logs/stratolink2_flight_state_relay_post_20260725_manifest.json \
  --scenario meshtastic --expect-fcnt-up-advance 1 \
  --min-relay-deduplicated 1 --min-relay-canceled 1 --min-relay-cad-busy 1 \
  --min-relay-hop-zero-drop 1 --min-relay-directed-drop 1 \
  --stimulus-evidence analysis/diagnostics/logs/stratolink2_meshtastic_stimulus_check_validated_20260725.json \
  --stimulus-evidence analysis/diagnostics/logs/stratolink2_meshtastic_stimulus_tx_validated_20260725.json \
  --stimulus-evidence analysis/diagnostics/logs/stratolink2_meshtastic_stimulus_cancel_validated_20260725.json \
  --stimulus-evidence analysis/diagnostics/logs/stratolink2_meshtastic_stimulus_hop0_validated_20260725.json \
  --stimulus-evidence analysis/diagnostics/logs/stratolink2_meshtastic_stimulus_directed_validated_20260725.json \
  --output analysis/diagnostics/logs/stratolink2_meshtastic_hil_20260725.json

python3 analysis/diagnostics/capture_flight_state.py \
  --label ctt_pre --profile joined-us
# Transmit the compatible physical CTT frame; require fPort 11 and the next
# primary uplink in TTN before taking the post-state.
python3 analysis/diagnostics/capture_flight_state.py \
  --label ctt_post --profile joined-us
python3 analysis/diagnostics/compare_operational_states.py \
  --before analysis/diagnostics/logs/stratolink2_flight_state_ctt_pre_20260725.json \
  --before-manifest analysis/diagnostics/logs/stratolink2_flight_state_ctt_pre_20260725_manifest.json \
  --after analysis/diagnostics/logs/stratolink2_flight_state_ctt_post_20260725.json \
  --after-manifest analysis/diagnostics/logs/stratolink2_flight_state_ctt_post_20260725_manifest.json \
  --scenario ctt --expect-fcnt-up-advance NN \
  --output analysis/diagnostics/logs/stratolink2_ctt_hil_20260725.json
```

Set `--expect-fcnt-up-advance` to the exact number independently visible in
TTN for each capture interval. Do not lower any minimum merely to make a
comparison pass; omit a scenario until its physical stimulus exists. The
`freefall-short` gate proves one cleanly armed genuine INT1 event entered one
burst cycle, produced the independently observed counter advance, exited on
restored gravity, consumed the wake flag, and did not trip chatter
suppression. It does not by itself prove the six-cycle stuck-low-g cap,
three-cycle cooldown, sixteen-clean-wake re-arm, or active-phase latency;
retain the sanitizer coverage and require separate physical pin/low-g timing
evidence for those claims. The
Meshtastic comparator proves the induced counter transitions, error-free
restore, and later FCnt reservation. It does not prove the forwarded raw
header by itself. The stimulus tool shares one serial interface between
transmit and passive observation, avoiding a port-ownership race; its log must
contain a
`local_origin_rf_echo` event with real RSSI/SNR, the expected decremented
`hop_limit`, and `next_hop=relay_node=0`. The validator and operational
comparator enforce that binding; otherwise anonymous forwarding remains
unproven.

## 9. Controlled retained-session corruption and recovery

After the downlink/B2B tests no longer need the current session, prove that a
non-marker data corruption cannot restore or transmit with it. Capture the
DevNonce journal first, then a fresh joined state:

```sh
python3 analysis/diagnostics/capture_devnonce_journal.py \
  --label crc_pre
python3 analysis/diagnostics/capture_flight_state.py \
  --label crc_pre --profile joined-us
python3 analysis/diagnostics/corrupt_tamp_session_hil.py \
  --label crc \
  --before-state analysis/diagnostics/logs/stratolink2_flight_state_crc_pre_20260725.json \
  --before-manifest analysis/diagnostics/logs/stratolink2_flight_state_crc_pre_20260725_manifest.json \
  --check-only
python3 analysis/diagnostics/corrupt_tamp_session_hil.py \
  --label crc \
  --before-state analysis/diagnostics/logs/stratolink2_flight_state_crc_pre_20260725.json \
  --before-manifest analysis/diagnostics/logs/stratolink2_flight_state_crc_pre_20260725_manifest.json
```

The guarded tool flips only bit 0 of TAMP session word 3 (retained DevAddr),
resets exactly once, waits ten seconds for setup/session restore, and performs
the frozen single-halt
RAM+TAMP read before resuming. Require its manifest to pass: session
magic/version remain intact, CRC alone is invalid, `_joined` is false,
`region_known` is false, the independent retained region lease is undamaged,
the observed DevAddr is exactly the one-bit mutation, and RAM/TAMP boot counts
both advance once. The raw state contains retained keys and remains private;
the decoded artifact is redacted.

Immediately prove that the rejection itself did not consume a join nonce:

```sh
python3 analysis/diagnostics/capture_devnonce_journal.py \
  --label crc_rejected
python3 analysis/diagnostics/decode_devnonce_journal.py \
  --before analysis/diagnostics/logs/stratolink2_devnonce_crc_pre_20260725.bin \
  --before-manifest analysis/diagnostics/logs/stratolink2_devnonce_crc_pre_20260725_manifest.json \
  --after analysis/diagnostics/logs/stratolink2_devnonce_crc_rejected_20260725.bin \
  --after-manifest analysis/diagnostics/logs/stratolink2_devnonce_crc_rejected_20260725_manifest.json \
  --expect-advance 0 \
  --output analysis/diagnostics/logs/stratolink2_devnonce_crc_rejection_20260725.json
python3 analysis/diagnostics/capture_flight_state.py \
  --label crc_fail_closed --profile cold-fail-closed
```

Recover with a real fresh GNSS fix when clear sky is available. If the
synthetic US bench authorization is still necessary, reapply it only through
the guarded action and prove the transition:

```sh
python3 analysis/diagnostics/apply_flight_hil_action.py \
  --action authorize-us --label crc_recovery \
  --before-state analysis/diagnostics/logs/stratolink2_flight_state_crc_fail_closed_20260725.json \
  --before-manifest analysis/diagnostics/logs/stratolink2_flight_state_crc_fail_closed_20260725_manifest.json \
  --check-only
python3 analysis/diagnostics/apply_flight_hil_action.py \
  --action authorize-us --label crc_recovery \
  --before-state analysis/diagnostics/logs/stratolink2_flight_state_crc_fail_closed_20260725.json \
  --before-manifest analysis/diagnostics/logs/stratolink2_flight_state_crc_fail_closed_20260725_manifest.json
# Wait for exactly one successful OTAA rejoin, primary uplink, and lease save.
python3 analysis/diagnostics/capture_flight_state.py \
  --label crc_authorized --profile authorized-us
python3 analysis/diagnostics/compare_hil_action_states.py \
  --before analysis/diagnostics/logs/stratolink2_flight_state_crc_fail_closed_20260725.json \
  --before-manifest analysis/diagnostics/logs/stratolink2_flight_state_crc_fail_closed_20260725_manifest.json \
  --action-manifest analysis/diagnostics/logs/stratolink2_flight_action_authorize_us_crc_recovery_20260725_manifest.json \
  --after analysis/diagnostics/logs/stratolink2_flight_state_crc_authorized_20260725.json \
  --after-manifest analysis/diagnostics/logs/stratolink2_flight_state_crc_authorized_20260725_manifest.json \
  --scenario authorize-us \
  --output analysis/diagnostics/logs/stratolink2_crc_reauthorize_hil_20260725.json
```

Using that same single observed rejoin, prove one and only one new nonce and a
clean joined session:

```sh
python3 analysis/diagnostics/capture_devnonce_journal.py \
  --label crc_rejoined
python3 analysis/diagnostics/decode_devnonce_journal.py \
  --before analysis/diagnostics/logs/stratolink2_devnonce_crc_rejected_20260725.bin \
  --before-manifest analysis/diagnostics/logs/stratolink2_devnonce_crc_rejected_20260725_manifest.json \
  --after analysis/diagnostics/logs/stratolink2_devnonce_crc_rejoined_20260725.bin \
  --after-manifest analysis/diagnostics/logs/stratolink2_devnonce_crc_rejoined_20260725_manifest.json \
  --expect-advance 1 \
  --output analysis/diagnostics/logs/stratolink2_devnonce_crc_rejoin_20260725.json
python3 analysis/diagnostics/capture_flight_state.py \
  --label crc_rejoined --profile joined-us
```

The normal loop can persist the synthetic lease. After all synthetic-region
link/downlink/relay tests, remove it through the paired guarded action and
prove that it caused exactly one reset, invalidated the retained lease, and
restored fail-closed RF silence:

```sh
python3 analysis/diagnostics/capture_flight_state.py \
  --label region_cleanup_pre --profile joined-us
python3 analysis/diagnostics/apply_flight_hil_action.py \
  --action clear-region-lease --label bench \
  --before-state analysis/diagnostics/logs/stratolink2_flight_state_region_cleanup_pre_20260725.json \
  --before-manifest analysis/diagnostics/logs/stratolink2_flight_state_region_cleanup_pre_20260725_manifest.json \
  --check-only
python3 analysis/diagnostics/apply_flight_hil_action.py \
  --action clear-region-lease --label bench \
  --before-state analysis/diagnostics/logs/stratolink2_flight_state_region_cleanup_pre_20260725.json \
  --before-manifest analysis/diagnostics/logs/stratolink2_flight_state_region_cleanup_pre_20260725_manifest.json
python3 analysis/diagnostics/capture_flight_state.py \
  --label region_cleanup_post --profile cold-fail-closed
python3 analysis/diagnostics/compare_hil_action_states.py \
  --before analysis/diagnostics/logs/stratolink2_flight_state_region_cleanup_pre_20260725.json \
  --before-manifest analysis/diagnostics/logs/stratolink2_flight_state_region_cleanup_pre_20260725_manifest.json \
  --action-manifest analysis/diagnostics/logs/stratolink2_flight_action_clear_region_lease_bench_20260725_manifest.json \
  --after analysis/diagnostics/logs/stratolink2_flight_state_region_cleanup_post_20260725.json \
  --after-manifest analysis/diagnostics/logs/stratolink2_flight_state_region_cleanup_post_20260725_manifest.json \
  --scenario clear-region-lease \
  --output analysis/diagnostics/logs/stratolink2_bench_cleanup_hil_20260725.json
```

A real fresh-fix clear-sky run remains mandatory before launch.

Do not declare the present single-balloon primary mission launch-ready while
the supercap charge/balance/transient reserve, exact-image clear-sky GPS,
flight-temperature behavior, installed antenna, EU868 exact-module margin,
hardened backend rollout, production registration, or primary TTN/downlink
loop remains unqualified. CTT is disabled in the StratoLink-2 flight image
because the fitted high-band module does not qualify 434 MHz; compatible-tag RF
evidence is required before restoring that feature claim, not as a precondition
for the intentionally CTT-disabled primary mission. Likewise, two-node RF and
durable transport freshness are mandatory before a multi-balloon B2B fleet,
but the current one-balloon launch has no peer transmitter and does not rely on
B2B for its primary TTN telemetry or command path.
