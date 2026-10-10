# Silent-flight recovery and regional provisioning

Evidence reviewed through 2026-10-10. See [candidate evidence](evidence.md) and
[remaining acceptance](acceptance.md) before treating any bench result as flight
qualification.

## What the silent flight established

StratoLink-2 flew on July 31 with candidate v16. It sent a fresh 12-satellite
packet and then a no-fix packet before launch; no postlaunch packet was observed
in the retained investigation. The payload was not recovered, so its failure
cause remains unresolved.

Two v16 policies could compound a GNSS or power fault:

- A reduced-power sleep lasted 1,800 seconds, but conservative clock accounting
  aged region authority by 1,953 seconds against a 1,800-second lease. The next
  wake needed two advancing GNSS epochs to regain permission to transmit.
- Failed GNSS standby confirmation shortened sleep to five seconds without a
  persistent retry budget. An awake receiver could prevent energy recovery.

Those are source-level mechanisms, not proof of the initiating flight fault.
Rail collapse, radio faults, assembly damage and coverage remain distinct
possibilities. A successful radio-driver return does not prove RF transmission;
a missing TTN packet does not prove GNSS failure.

October bench work exposed separate acquisition, shutdown and radio-path issues.
The later integrated image has real recovery evidence, but the October 9 reset
and 66-minute reception gap remain unexplained. Neither that recovery nor a
short preflight fix establishes final-power endurance.

## Preserve evidence before intervention

1. Record the fitted assembly, power sources, antenna arrangement and last
   known BIN/ELF hashes. Distinguish an intentionally unpowered board from an
   operating board with missing telemetry.
2. Retain raw TTN packets before the deployment's configured storage retention
   expires. Keep server reception separate from laptop MQTT capture; a sleeping
   laptop can lose local records while TTN continues receiving them.
3. Preserve the board baseline and nonce journal before a planned flash or
   reset. Flash/RAM exports may contain keys and must remain private. Decode
   only the state needed for the investigation.
4. Compare boot/reset state, frame counters, fix freshness and authority expiry
   with power and RF observations. Record debugger attachments, resets, power
   changes and test stimuli as interventions.
5. Use a bounded fault test with a known restoration image. Verify the restored
   image and the following natural primary; do not silently promote a diagnostic
   profile to flight status.

## Provision the intended board

The October 5 audit initially found only Board 1's US registration. Separate
EU, AS and AU registrations were subsequently created and read back, followed
by private-header provisioning. This is historical registration evidence, not
current registry verification or proof of regional RF performance.

For a new candidate:

1. Audit the selected board profile, command address and each intended regional
   identity against its TTN registration. Header filenames alone do not establish
   hardware ownership. Confirm the exact module supports the required bands.
2. Preserve existing identities, nonce history and the physical nonce journal.
   Never substitute another board's credentials or initialize a used identity
   from a blank or stale nonce seed.
3. Create only verified-missing registrations under one operator's ownership.
   Retain generated credentials privately before writes. Resolve ambiguous
   responses by readback; do not blindly retry creation or replace live records.
4. Merge only the reviewed regional values into the ignored board header, then
   audit identity, feature flags, fleet key and power gates again. Use a private
   fleet key for operational B2B tests, not the public diagnostic key.
5. Install the reviewed device formatter and verify its exact source. Registry,
   header, formatter, build and flash checks are separate records.
6. Treat retained launch authority as an explicit, bounded operation for the
   known physical region. Its development rearm is a bench action, not a flight
   workaround for failed GNSS. Final acceptance must identify the authority
   source and demonstrate a fresh GNSS region decision.

The diagnostics contribution provides `preserve_board1_baseline.py`,
`board1_provisioning_audit.py`, `provision_board1_ttn_regions.py`,
`merge_board1_regional_header.py`, `install_board1_regional_formatter.py` and
`provision_board1_launch_authority.py`. Read each tool's current arguments and
target checks before use. Preservation can interrupt the MCU; the registration,
formatter, header and launch-authority operations change their named targets.

Website deployment and database migration remain a separate handoff to the
site owners. They do not replace board, GNSS, RF or energy qualification.
