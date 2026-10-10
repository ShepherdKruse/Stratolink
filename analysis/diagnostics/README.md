# Bench and telemetry tools

These tools support the flight firmware and its offline regression tests. They
do not certify a payload for launch. Captures, credentials, generated manifests,
BIN/ELF files and precise flight routes stay out of Git.

## Offline checks

Use Python 3.11 or 3.12, Node, a C++ compiler and PlatformIO. From the repository
root, create a virtual environment and install the diagnostic dependencies:

```sh
python3 -m venv analysis/diagnostics/.venv
analysis/diagnostics/.venv/bin/pip install -r analysis/diagnostics/requirements.txt
pio run -d firmware -e stratolink
bash analysis/diagnostics/run_host_suites.sh
analysis/diagnostics/.venv/bin/python analysis/diagnostics/run_offline_tests.py
```

The offline runner names each test explicitly. Do not discover and execute every
`*_test.py`: `ttn_downlink_test.py` is an operator command that can queue real
downlinks. The runner uses synthetic records, fake transports and temporary
files. Memory/source checks require the local PlatformIO build and its libraries.
Python tests alone do not establish RF delivery, current draw or power margin.

## Hardware and provisioning

Read each command's `--help` and inspect its targets before use. Tools named
`board1` retain explicit StratoLink-1 identity and registry checks; they are not
fleet-wide provisioning commands. Credentials come from ignored local files or
environment variables, never from checked-in fixtures.

- `generate_flight_hil.py` binds symbol addresses and hashes to the supplied ELF
  and BIN. It generates J-Link scripts but does not execute them. Generated scripts
  include intrusive read, flash and region-clear operations; inspect each before
  running it. Toolchain lookup uses PATH, then `PLATFORMIO_CORE_DIR` or
  `~/.platformio`.
- `preserve_board1_baseline.py` captures private flash and state with create-once
  output. Even an inspection can halt the MCU. Its reset-assisted development
  path is a separate explicit option.
- `flash_board1_development.py` requires a caller-supplied BIN hash and full flash
  baseline, and preserves the reserved nonce page by default. It is a development
  flasher, not a qualification gate.
- `provision_board1_ttn_regions.py`, `merge_board1_regional_header.py` and
  `install_board1_regional_formatter.py` perform guarded, explicit writes to
  their named registries or private header. Formatter source is pinned to the
  reviewed canonical file under `web/public/assets/docs`.
- `provision_board1_launch_authority.py` changes retained RF authority. Use only
  for the known physical region and preserve its before/after evidence.

Old wrappers pinned to a frozen July image are not included. Regenerate manifests
for each build; the synthetic decoder manifest is only a test fixture.

## Soak capture and radio tests

`ttn_soak_monitor.py` captures MQTT into a new log. It needs a continuously running
host and network. `ttn_uplink_archive.py` normalizes retained TTN records, while
`ttn_storage_presence_audit.py` and `ttn_decoded_comparison.py` compare coverage
and wire fields. TTN retention must cover any period without a collector; a
sleeping laptop is not an always-on archive.

`ttn_storage_replay.py` is dry-run by default. Its `--apply` path posts retained
uplinks to a deployed, authenticated, idempotent webhook. Coordinate replay and
database changes with the site owners. `supabase_migration_local_check.py` is a
separate opt-in integration check using a disposable, network-disabled local
Postgres container. It does not test production API authorization or PostGIS.

Mesh and two-node HIL tools require compatible independent LoRa peers. Flipper
CTT scripts package synthetic valid and bad-CRC frames; hardware staging and
transmission require explicit options and serial selection. Their nominal power
labels are not calibrated receiver-margin measurements. The offline IQ decoder
does not transmit, and an RTL-SDR cannot replace a LoRa transmitter.

Energy and antenna audits expose historical model assumptions. Supply the
requested measurements or captures, and keep modeled budgets separate from
measured final-assembly performance.

Required model inputs are explicit:

- Charge ceiling: `--flight-power CSV`.
- Mission sizing: `--night-reserve JSON --balance JSON --airtime JSON
  --darkness JSON --power-model relay_power_budget.py`.
- Vendor screen: `--mission-audit JSON` from the sizing command.
- Flight-3 darkness: `--telemetry CSV --reconstruction NPZ --night-reserve JSON`.
- Launch darkness: `--night-reserve JSON`.
- RF band audit: `--telemetry CSV`.

The JSON arguments are outputs from the named audits. The power-model source is
part of the separate research contribution or can be supplied by the operator.
Synthetic test inputs are not substitutes for measured flight evidence.
