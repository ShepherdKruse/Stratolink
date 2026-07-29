# StratoLink-2 wake-up critical path

Prepared 2026-07-27 for the planned Friday 2026-07-31 launch. The controlling
decision remains **NO-GO** until every required physical and production gate is
closed with passing evidence.

## Before touching the rig

1. **Do not touch J-Link or the target.** The automatic extension failed before
   PPK2 access because its queued interpreter lacked `pyserial`. The immutable
   record
   `stratolink2_soak_retry_20260725_failed_extension_handoff_20260727.json`
   reports a 110.049-second rescue transition against the required 0-2 seconds.
   No passing extension summary exists or may be manufactured from this run.
2. Confirm the fresh PPK2 supervisor is still emitting 4,660 mV heartbeats with
   zero reconnects. The original rescue was deliberately ended only after a
   corrected holder was armed; the fresh holder is now
   `stratolink2_soak_retry2_20260727_power.jsonl`. It began at
   `2026-07-27T09:47:54.388Z` and must run 86,400 seconds. Its separately
   preflighted standby will create
   `stratolink2_soak_retry2_20260727_handoff.jsonl` only after `hold_end`.
3. Keep the solar panels fully covered. Do not move the board, USB wiring,
   Tag-Connect, or J-Link; do not install C5.
4. Confirm
   `stratolink2_ttn_devstatus_postchange_phase2b_20260727.json` reports
   `PASS_CLEAN_FOLLOWING_UPLINK`. The earlier phase-2 artifact is deliberately
   retained as a watcher-specification failure: it redundantly required an
   unstable Network Server audit event even though Application Server receive,
   forward, and Storage directly proved the same hop. Phase 2b contains no MAC
   unanswered/request/downlink event and all regional pending counts are zero.

## Controlling Friday decision

The intended 0.8-1.2 F C5 range fails the already-incomplete launch-night
energy screen. At the full tolerance-lower charge corner, 1.2 F provides only
5.806-5.950 h before the conservative 3.32 V accounting floor, versus an
8.667 h launch night. The lower-bound model still omits sensors, WFI MCU,
failures, joins/retries, cold, aging, weather, sag, and reserve. The current
8.25 MOhm charge divider can also exceed the 5.5 V absolute maximum, and C5's
midpoint is unconnected with no internal balance.

Therefore a Friday circumnavigation launch cannot become GO merely by soldering
the planned capacitor or swapping R1. The safe choices are:

- postpone while a larger, balanced, voltage-safe store is designed and
  qualified; or
- explicitly redefine the mission and acceptance criteria before testing.

The latter is not equivalent to qualifying the existing circumnavigation
mission and must not be represented as such.

## Precursor preservation is prohibited on this attempt

The failed 0-2-second handoff gate explicitly prohibits precursor preservation,
target halt/reset, and flashing. Do not run the previously prepared manual
commands and do not invoke J-Link directly. The new clean retry above must
complete its 86,400-second hold and qualified 0-2-second automatic handoff
first. The exact 262,144-byte pre-retry baseline and required SHA-256 remain
unchanged, but they are not authorization to access the target.

## Remaining sequence after a new clean retry and successful preservation

1. Finish source review, then freeze and verify a newly numbered candidate
   (planned v10) with zero failures and an isolated byte-identical rebuild.
2. Flash only through `flash_flight_candidate.py`, check-only then actual, with
   explicit retry summary, sensor model, handoff log, candidate verification,
   and precursor manifest. Require byte verification and option-byte readback.
3. Run exact-image focused HIL: clear-sky two-epoch GNSS/value rejection,
   airborne-mode readback, reset recovery and standby; sensors/freefall;
   watchdog/STOP1/reset cause; LoRaWAN join/uplink/downlink/session/counters;
   Meshtastic restore/CAD; and available CTT/B2B stimulus.
4. On the qualified fitted energy-store assembly, measure total and both cell
   voltages, current, sag, tier crossings, actual BOR, darkness endurance,
   sunrise recovery, solar charging, and the -42.1 C observed flight envelope.
5. Complete exact-assembly NanoVNA sweep and physical inspection. KiCad 10 CLI
   still crashes before producing a current DRC report; obtain a successful GUI
   export or independent layout review and disposition every surviving finding.
6. Register `stratolink-2`, deploy the pinned production migrations and webhook
   authentication, prove exactly-once ingestion/retry plus a primary
   uplink/downlink loop, and rotate all TTN/Supabase credentials disclosed during
   testing. Retain the now on-air-proven zero DevStatusReq periodicities through
   this rollout; arbitrary MAC commands remain unsupported by the current
   flight implementation.

## Scope controls

- Candidate v9 and every earlier candidate are superseded and must not be
  flashed. The current build output is transitional, not an eligible candidate.
- The current relay-soak does not prove flight-profile STOP1 current,
  supercapacitor reserve, auxiliary-window entry without post-soak counters, or
  the exact final binary.
- Wildlife-tag collection is disabled in the flight image because the fitted
  high-band RAK3172 does not qualify 434 MHz.
- A single-balloon TTN mission does not depend on B2B, but no replay-robust fleet
  claim is allowed without a second node and delayed/reset RF evidence.
