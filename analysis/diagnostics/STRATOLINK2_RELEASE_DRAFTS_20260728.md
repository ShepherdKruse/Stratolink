# StratoLink-2 release drafts

These are drafts only. Nothing is staged or committed.

## Recommended commit sequence

1. `firmware: harden flight loop, GPS freshness, and retained state`

   Require two advancing GNSS epochs and valid physical values, fail closed on
   stale region authority, persist LoRaWAN counters and DevNonce safely, harden
   sensor and radio recovery, and make STOP1 progress and reset behavior
   observable.

2. `radio: add Meshtastic relay, wildlife events, and balloon mesh`

   Add delayed CAD-aware LongFast relay behavior, CTT wildlife decoding and
   queued fPort-11 events, authenticated B2B crumbs and commands, bounded
   deduplication and airtime accounting, and exact PHY restore checks.

3. `backend: support telemetry v2 and auxiliary radio records`

   Decode the 40-byte telemetry-v2 payload, command ACK and relay state, sensor
   unavailable sentinels, wildlife events, and B2B packets. Add authenticated
   webhook ingestion, idempotency, schema constraints, and production
   registration paths.

4. `test: add exact-image HIL and launch qualification evidence`

   Add strict sanitizer suites, embedded build coverage, source and memory
   audits, guarded J-Link workflows, PPK2 continuity and current profiling,
   TTN Storage checks, sensor models, and create-once evidence manifests.

## Pull request title

`Prepare StratoLink-2 flight firmware and telemetry v2 for launch`

## Pull request body

### Summary

This change set brings the post-Flight-3 firmware, radio services, telemetry,
backend contracts, and qualification tooling together for StratoLink-2.

The main objective is to preserve the parts of Flight-3 that worked while
closing the stale-GPS and observability gaps that made later dropouts hard to
diagnose. It also adds the requested Meshtastic relay, wildlife tag collection,
and authenticated balloon-to-balloon mesh paths.

### Flight firmware

- Require two forward-moving GNSS PVT epochs before accepting a fix.
- Reject stale, frozen, checksum-invalid, or physically impossible PVT data.
- Clear position, motion, and satellite fields when no fresh fix is available.
- Reapply and verify the airborne dynamic model after receiver wake or reset.
- Bound GNSS recovery by rail voltage and confirm standby before long sleep.
- Select LoRaWAN region from fresh position and fail RF-quiet when the retained
  region lease is missing, corrupt, or expired.
- Persist DevNonce, session counters, command sequence, relay state, boot count,
  region lease, and B2B origin IDs with corruption and torn-write checks.
- Reserve uplink counters before RF so resets cannot replay a transmitted frame.
- Harden STOP1, watchdog chunking, freefall wake handling, radio quiescence,
  sensor recovery, and unavailable-sensor telemetry.
- Add exact reset, radio, GNSS, sensor, command, relay, and wildlife counters for
  hardware qualification.

### Radio services

- Add a solar and rail-gated Meshtastic LongFast window on supported regional
  frequencies.
- Relay only eligible flood traffic after a delayed ROUTER_LATE contention
  window, cancel duplicates, require clear CAD, and restore the LoRaWAN PHY.
- Add CTT wildlife frame validation, bounded queueing, event age, and typed
  fPort-11 uplinks. The flight default remains disabled until supported-band RF
  is proven on the fitted module.
- Add authenticated B2B crumbs, commands, ACKs, TTL handling, deduplication,
  bounded queues, delayed forwarding, and fPort-12 tunneling.
- Keep auxiliary radio work subordinate to legal region authority, VSTOR,
  solar, watchdog, freefall, and primary LoRaWAN delivery.

### Telemetry and backend

- Extend the primary payload from 35-byte v1 to 40-byte v2 while retaining the
  original field prefix.
- Add power tier, reset cause, boot count, GNSS fix age, durable command ACK,
  actual relay state, relay-forward delta, and wildlife-tag delta.
- Encode failed or skipped environmental channels as explicit unavailable
  sentinels instead of plausible zero values.
- Make raw LoRaWAN payload bytes authoritative over formatter JSON.
- Add strict payload length and value validation, authenticated webhook intake,
  exact-index idempotency, and telemetry, wildlife, and B2B schema support.
- Keep 35-byte historical packets readable.

### Qualification completed

- All strict ASan and UBSan host suites pass.
- All embedded PlatformIO environments pass.
- Strict warning and analyzer compilation passes.
- Web type checking, linting, host vectors, and production build pass.
- Retry-3 ran 86,400.113 seconds at 4,660 mV with zero reconnects and 69
  contiguous TTN uplinks.
- Candidate v15 has a zero-failure immutable verification report and an
  isolated byte-identical rebuild.
- Exact v15 completed US915 OTAA and fresh FCntUp 0 through 3.
- A real TTN PING with sequence 160 was persisted across reset and echoed as
  `command_ack_seq=160` on the next uplink.
- The pre-supercap STOP1 profile measured 6.730 uA median, and exact v15
  measured 6.688 uA median with all selected bins below 10 uA.
- The complete DevNonce journal remained byte-identical through profiling and
  exact-image restoration.
- Passive protocol and SDR captures confirm nearby LongFast stimulus.

### Remaining physical and deployment checks

- Run clear-sky GNSS on the exact image and compare position and fix freshness.
- Fit the selected energy store, then repeat room-temperature, cold, load-step,
  and darkness endurance tests on the completed assembly.
- Use StratoLink-1 as the second radio for Meshtastic forwarding, authenticated
  B2B crumb and command exchange, delayed-age behavior, and CTT tag emulation.
- Sweep the installed antenna and completed assembly.
- Apply and verify the production database migrations, deploy the hardened
  webhook, register StratoLink-2, and validate NA, EU, AS, and AU credentials.

### Exact candidate

- ELF: `8fa10da859b2c542d244cb2f62bebcf388730cbeea9eb4746a94c2d50e3d91f8`
- BIN: `920f57c139236b6097caec8936cefe681f82fa3b4c4e084f2861ad54bd1ae20d`

## Text to Caleb and Shepherd

StratoLink-2 firmware is at the release-candidate stage. The exact v15 image
has passed the full software verification matrix, a 24-hour powered soak,
fresh TTN uplinks, a real downlink PING with reset-persistent ACK, and a
pre-supercap STOP1 profile below 7 uA median. The backend work is ready to pick
up: apply the telemetry v2, wildlife, B2B, and ingest-integrity migrations;
deploy the hardened TTN webhook; register stratolink-2; and verify the NA, EU,
AS, and AU integrations. I will send the PR once I finish the two-board and
fitted-supercap checks. Please do not copy credentials into chat or the repo.
