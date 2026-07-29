# StratoLink-2 Friday launch decision brief

Prepared 2026-07-27 for the planned Friday 2026-07-31 launch. This is a
fail-closed decision sheet. It does not replace the detailed evidence matrix or
post-soak HIL runbook. The ordered operator handoff is
`STRATOLINK2_WAKEUP_CRITICAL_PATH_20260727.md`.

## Disposition

**NO-GO.** The fresh clean relay-soak and source hardening are progressing, but required
physical, target-preservation, exact-image HIL, and production gates remain
open. No amount of additional 4.660 V bench uptime can close the missing
energy-store, charge/balance, cold, antenna, backend, or clear-sky GNSS gates.
The later 86,400-second preservation hold passed, but its automatic extension
failed before PPK2 access because the queued interpreter lacked `pyserial`.
Rescue acquisition was 110.049 seconds after `hold_end`, outside the required
0-2 seconds, so this attempt also forbids precursor preservation and all J-Link
target access.

A third, fully fresh 86,400-second retry began at
`2026-07-27T09:47:54.388Z` with a dependency-preflighted standby process and a
separate pass-only watcher already waiting. At `2026-07-27T14:17:49.149Z` it
had held 16,195.620 seconds at exactly 4.660 V with zero reconnects; all 531
completed assertion gaps were at or below 30.459 seconds. TTN fCnt 3-12 were
contiguous after collector start, with VSTOR 4.570-4.616 V. TTN fCnt 13 then
arrived at `2026-07-27T14:13:28.965396247Z`, extending that sequence through
13 without changing the VSTOR bounds. The complete
non-mutating regression matrix also passed again after the 51-symbol exact-HIL
observability update, skipping only the deliberately stale v9 identity test.
This is healthy
progress only; it cannot pass until the terminal gap and 0-2 second handoff
plus later standby heartbeat are recorded.

## Evidence already passing

- Clean retry: 57,600.195 seconds at 4.660 V, zero PPK2 reconnects, and all
  assertion gaps at or below 30.507 seconds.
- Standby supervisor takeover: 1.443 seconds at 4.660 V with a later heartbeat.
  This proves bounded source takeover, not rail/execution continuity; the
  no-supercap payload likely rebooted during the transfer.
- TTN/backend retry set: 47 contiguous fCnt 63-109 uplinks and 47 exact
  Supabase counterparts; the frozen TTN file is 30,260 bytes with SHA-256
  `37c861f7a0d5a533e97e7bb0246faf69c9ec9c98386f5ac38c87d79350ea47a5`.
- Candidate v9 historically verified with zero failures: ELF SHA-256
  `3436cd9b027b19ee110486810ea79686533a341f0566771e6fdd712421778241`;
  BIN SHA-256
  `23fdec5f76da71432060b9c5ba05a19447378b827e1084d3f0ac2cc300c7a7d4`.
  It is now superseded along with every earlier candidate and must not be
  flashed: continued loop review found and repaired a STOP1 scheduler
  live-lock/short-wake energy path. The transitional revision passes all 29
  strict ASan/UBSan host suites, zero strict-warning and GCC `-fanalyzer`
  diagnostics across 33 flight sources, and all 13 embedded builds. A second
  review finding is also repaired: STM32duino's malloc-backed `operator new`
  could return null while GCC assumed success and invoked a RadioLib constructor
  through it. The source now uses `-fcheck-new`, staged module/HAL/radio
  allocation, complete failure cleanup, and a HIL-gated diagnostic counter;
  emitted ARM code proves both pre-constructor null branches. Packet storage is
  now derived from the public payload ceiling, CMAC rejects overflow-sized
  input, and B2B encoding receives the caller's real capacity. The freefall ISR
  latch also uses atomic consume plus a generation check so cleanup cannot erase
  an overlapping wake; exact ARM disassembly proves the exclusive operations
  and barriers. The retained region lease now also reserves 300 seconds at the
  start of every warm boot, before external-peripheral work, so resets cannot
  discard active time and indefinitely preserve a stale frequency plan. The
  LIS2DH12 clear path now also requires a successful sample plus positive
  non-freefall magnitude; an I2C failure can no longer dismiss a real descent
  wake, and persistent unknown/low-g state remains bounded by the six-cycle
  burst cap and cooldown. A subsequent energy audit also found that an unready
  radio formerly bypassed SX1262 sleep; one 1,200-second STDBY_RC interval can
  consume 65.4% of the specified-minimum capacitor's screened reserve. Ready,
  unready, and first-sleep-failure paths now require confirmed radio sleep after
  one bounded reinitialization or reset before the long idle interval. The same
  review found an independent LTR390 leak path: a failed I2C transaction after
  enable could leave up to 200 uA active for the complete sleep interval. The
  driver now requires exact standby readback, falls back to a verified software
  reset, preserves the primary tracking/Class-A control exchange, suppresses
  optional CTT/B2B TTN, and makes five bounded 60-second bus/quiescence-only
  retries with all auxiliary service windows closed. A persistent non-critical
  optical fault then resumes normal primary GPS/TTN cadence in degraded mode,
  with optical reads and every auxiliary service still disabled, so it cannot
  age the regional lease forever or silence tracking. A newly
  numbered,
  isolated-byte-identical, zero-failure candidate is still required after the
  source review ends.
- A later low-power review found that STM32duino's normal ADC stop path clears
  `ADEN` but leaves the STM32WLE5 ADC internal regulator and VREF path enabled.
  RM0461 explicitly requires disabling the regulator before Stop mode. The
  source now clears VREF, invokes the HAL regulator-disable path, verifies
  `ADEN`/`ADVREGEN`/`VREFEN`, uses a bounded peripheral-reset fallback, gates
  both the ADC run and sleep clocks, and resets rather than enter STOP1 if the
  readback still fails. The post-fix source passes all 29 strict ASan/UBSan
  host suites, all 33 strict warning/`-fanalyzer` source compilations with zero
  diagnostics, all 13 embedded environments, `git diff --check`, and the full
  non-mutating diagnostic matrix except the deliberately stale v9 identity
  binding. This is source evidence only; the exact final image still requires
  a dedicated `stratolink_profile` PPK2 current run.
- A cross-layer sensor-integrity review found that an unavailable
  environmental read inherited zero-filled packet fields, so a failed
  temperature, acceleration, or optical channel could masquerade as 0 °C,
  zero-g, or darkness. The transitional source now uses explicit impossible
  wire sentinels for temperature, pressure, atomic XYZ acceleration, UV, and
  lux; genuine optical saturation remains distinct. Both TTN decoders map
  these states to null, reject mixed-axis validity, and the final soak/model
  gates reject any unavailable required sensor. This repair also corrected the
  Python collector's latent signed-pressure format typo. A downstream UI audit
  also centralized mobile numeric conversion so null, undefined, blank, NaN,
  and infinity remain unavailable rather than becoming a plausible zero; its
  focused host vectors and complete web verification pass. All 29 strict host
  suites, all 13 embedded environments, web verification, strict analyzer,
  heap/stack audits, and the full non-mutating matrix pass after the firmware
  change.
  The existing valid v2 acoustic/power codes remain wire-compatible, while five
  formerly invalid lower-nibble values now report microphone unavailable at
  each power tier. A skipped or failed capture can no longer masquerade as
  quiet; exact-image counters remain necessary to separate the reason and to
  validate detector response in HIL.
- A Class-A receive-boundary audit found that the data-down path could truncate
  an oversized RF frame to 64 bytes and authenticate only that prefix. It now
  matches OTAA: the complete candidate is rejected, the absolute receive window
  re-arms, and no prefix reaches MIC/decryption. The pure decoder and
  source-bound regression pass; exact-image oversized-then-valid RX1/RX2 HIL is
  still mandatory.
- The post-soak release chain is now independently fail-closed at the flash
  boundary. Preservation records the still-growing standby log as an immutable
  append-only prefix. Before any candidate write, the flash wrapper rechecks
  the fixed 256 KiB pre-retry hash, byte-identical post-soak dump, IWDG-in-STOP
  option bit, every immutable preservation input, the standby prefix, current
  4.660 V power, and zero reconnects. Adversarial regressions reject a false
  unchanged-flash claim, wrong baseline record, changed provenance, stale
  standby heartbeat, and any pre-existing output artifact. The v10 freeze path
  now also makes the exact-ELF heap and stack audits create-once, requires both
  reports to pass against the candidate hash, and carries their SHA-256
  provenance inside the immutable candidate report that preservation and
  flashing revalidate.
- GPS stale-fix defenses are source- and host-proven: advancing two-epoch
  freshness, reset invalidation, physical-value rejection, airborne-mode
  readback, bounded wedge recovery, and atomic no-fix telemetry all fail
  closed. Clear-sky exact-image HIL is still required.
- The NA/EU/AS TTN Network Server records now explicitly disable both
  DevStatusReq periodicities, with guarded preflight and readback at HTTP 200
  for every region. This removes a periodic MAC request the compact stack does
  not answer without changing the flight implementation. The first post-change uplink
  retired the one already-sent request without scheduling a replacement. The
  next uplink at `2026-07-27T08:39:34.223341220Z` reached Network Server,
  Application Server, webhook forwarding, and Storage with no DevStatus,
  unanswered, or downlink-schedule event; NA/EU/AS pending counts remained
  zero. The server-side remediation is closed. Application-downlink HIL remains
  mandatory.
- The same three regional Application Server webhooks no longer send unused
  join-accept bodies to the uplink-only ingestion route. A guarded field-mask
  update cleared only `join_accept`; readback retained `uplink_message` in all
  regions. This closes the configuration cause of the join-correlated
  `as.webhook.fail` observed after the failed power handoff. The first following
  uplink reached Network Server, Application Server, TTN Storage, and exactly
  one Supabase telemetry row. The event stream omitted its Storage audit event,
  so the first watcher remains failed; a corrected artifact binds the direct
  Storage and Supabase records instead. This does not close the absent
  production database schema or device registry.
- The first post-transition row also passes a narrow sensor/reset check:
  atomic NOGPS rather than stale coordinates, plausible room pressure and
  temperature, approximately 1 g stationary acceleration, shaded optical
  inputs, 4.604 V VSTOR, and a strong SF9 US915 link. This is one precursor
  sample—not calibration, clear-sky GNSS, environmental, or final-image HIL.

## Non-negotiable Friday blockers

The energy-store remediation and exact pass/fail sequence are consolidated in
`STRATOLINK2_ENERGY_STORE_DECISION_20260727.md`.

1. **Energy store absent and architecture unqualified.** C5 is not fitted; its
   midpoint pad is open and the module has no internal balancing. The present
   charge divider screens to 5.591979 V against 5.5 V absolute maximum. Keep
   the panels fully covered and do not install C5 until the divider, balancer,
   cleaning, polarity, and controlled-light procedure are reviewed.
2. **No screened divider closes long-duration energy.** Historical clear-sky
   darkness reached 9.674 h. At the Flight-3 high-latitude screen, the July 31
   launch night is 8.667 h, the first 30 days reach 10.091 h, and 90 days reach
   13.252 h. The optimistic 7.32 MOhm minimum-cap baseline is exceeded August
   7 and the 7.50 MOhm reference August 16, before active loads or weather.
   Adding only typical hot-GNSS, primary-TX, and mandatory empty Class-A RX
   cuts the 0.8 F tolerance-lower screen to 3.509/3.798 h. Even this incomplete
   model gives the specified 1.2 F maximum only 5.806/5.950 h, so every
   tolerance bin of the planned part fails launch night. It requires at least
   1.822/1.779 F for launch night and 2.764/2.662 F for the 90-day seasonal
   night at 7.32/7.50 MOhm. Omitted loads only increase it.
   An official CAP-XX HY-series comparison now identifies active-balanced
   2.5 F, 3.5 F, and 5 F reference modules. The 2.5 F minimum clears only the
   launch-night lower screen, 3.5 F clears the first 30 days, and 5 F clears
   the modeled 90-day night. None fits C5 or is stocked, mounted, mass-reviewed,
   electrically integrated, or qualified; this is a future architecture path,
   not a Friday substitution.
3. **Precursor not preserved.** Check-only passed against the exact 262,144-byte
   pre-retry flash baseline and SHA-256
   `fd6ed6053206ddfe63ab40c7333752b383ad5f71caa07af3c334e5da4d5891f9`,
   but the actual J-Link read was rejected before target access by the desktop
   external-action limit. The subsequent extension handoff also failed: the
   86,400.119-second primary was clean, but no extension log was created and
   rescue began 110.049 seconds later. No precursor artifacts exist. Do not
   halt, reset, flash, or access the target directly around either gate; a new
   clean 86,400-second handoff retry is required.
4. **No eligible exact candidate exists yet.** Candidate v9 and earlier are
   superseded. Freeze a newly numbered candidate only after source review ends
   and precursor preservation byte-compares the complete post-soak flash; the
   guarded wrapper must then pass check-only and actual modes. Then GNSS, sensors,
   STOP1/watchdog/reset, LoRaWAN session/counters/downlink, Meshtastic restore
   and CAD, and available CTT/B2B behavior require focused HIL.
5. **Flight assembly is not environmentally qualified.** Clear-sky GNSS,
   exact-assembly cold HIL through the observed -42.1 C envelope, fitted-cap
   darkness/sag/BOR/sunrise recovery, exact-assembly NanoVNA sweep, and current
   PCB DRC/manual inspection remain open.
6. **Production path incomplete.** Register `stratolink-2`, apply the pinned
   migrations, configure a dedicated webhook secret, prove authenticated
   exactly-once ingestion and retry behavior, and complete the primary
   uplink/downlink loop. Rotate the TTN and Supabase credentials disclosed
   during testing before release. A fresh publishable-key-only zero-row probe
   still returns missing-column `42703` for telemetry and PGRST205 for both
   event tables, so this is a current production failure—not a stale checklist
   item.
   The connected Supabase management integration is also scoped to an unrelated
   project and receives permission denied for the StratoLink project. No
   production mutation was attempted; correct project-bound management access
   is now an explicit prerequisite.

## Scope controls

- The flight image intentionally disables 434 MHz wildlife-tag listening
  because the fitted `RAK3172-9-SM-NI` high-band module does not substantiate
  434 MHz reception. Do not claim bird-tag collection without a compatible
  transmitter and launch-relevant receive-margin proof.
- One-balloon primary TTN telemetry does not depend on B2B. Do not claim a
  flight-qualified B2B fleet until a second StratoLink node closes delayed
  crumb-age, replay, reset, and two-node RF gates.
- The relay-soak is deliberately aggressive and does not prove
  flight-profile STOP1 current or minimum-capacitor endurance.

## Overnight rig state

Leave the fresh PPK2 supervisor running, keep the computer awake, keep
the panels fully covered, and do not move the board, J-Link, or USB connections.
The rescue was safely handed to a fresh 86,400-second qualification holder at
`2026-07-27T09:47:54.388Z`; its new path is
`stratolink2_soak_retry2_20260727_power.jsonl`. The corrected project-venv
standby is already dependency-preflighted and queued. Neither the failed run nor
the in-progress retry authorizes target access.

At `2026-07-27T13:12:22.068Z`, the fresh retry had reached 12,268.566
seconds at exactly 4,660 mV with zero reconnects and no early standby access.
Its dedicated MQTT collector had recorded contiguous FCntUp 3-10 at the
expected approximately 21-minute cadence. Observed VSTOR was 4,570-4,616 V;
the 4,570 V minimum is only 10 mV above the final 4,560 mV source-floor gate.
That is a watch condition, not a completed pass or evidence of supercapacitor
reserve.

## Minimum path to reconsider GO

Reconsideration requires every blocker above to have create-once, hash-bound
passing evidence. If the energy architecture, precursor preservation, exact-
image HIL, clear-sky GNSS, cold/fitted-cap qualification, antenna/PCB review,
and hardened production loop cannot all close before Friday, postpone. A
shorter mission objective does not make a circumnavigation-capable payload safe
unless the launch scope and acceptance criteria are explicitly changed before
testing.
