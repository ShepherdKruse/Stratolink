# Class-A downlink command channel: analysis + protocol spec

A minimal, application-layer, RX2-only, FULL-tier-gated Class-A receiver plus a tiny
safe command set, so we can dial in settings mid-flight without ever being able to
brick a balloon that has no reset button at 12 km. Designed addressable from day one
so balloon-to-balloon store-and-forward can carry commands over the ocean later.

Substantiated against the LoRaWAN spec (L2 v1.0.4, RP002-1.0.3), TTN docs, other
pico-balloon flights, and our own flight-3 data. Build single-balloon over-land first.

---

## 1. How it works (mechanics)

**No uplink, no downlink.** Class A is the lowest-power class: the network can only
reach the device in two short RX windows that open right after the device transmits.
There is no asynchronous downlink path. So a command rides our existing 20-min cadence:
the network queues it, we collect it on our next uplink's RX window.

- **RX1** opens at RECEIVE_DELAY1 (default 1 s) on the uplink channel, data rate offset
  down. Our SF9 (DR1) US915 uplink maps to an RX1 downlink at DR11 = SF9/BW500.
- **RX2** opens at 2 s on a fixed frequency + data rate. US915: 923.3 MHz / DR8 =
  SF12/BW500 (RP002 default, confirmed in a real pico-tracker log below).
- **TTN deviation that bites a from-scratch stack:** TTN configures EU868 RX2 at the
  non-standard SF9/BW125 (DR3) on 869.525 MHz, not the spec-default SF12. We must use
  SF9 there or miss every EU downlink.
- RX_DELAY is tunable 1 to 15 s via the Join-Accept RxDelay field. The spec explicitly
  says to size the window for "maximum potential imprecision of the device clock."

Our uplink behaviour is unchanged: SF9, 1200 s cadence, ~308 ms ToA, 22 s/day = 74% of
the uplink FUP. Receiving adds zero transmit airtime.

---

## 2. Airtime + FUP (does this change how often we can transmit? No.)

We are only receiving. The gateway (a different device) transmits the downlink, and
that airtime is charged to the gateway's duty cycle and TTN's downlink budget, not our
FUP. Our SF, cadence, and uplink airtime are untouched.

- **TTN caps downlinks at ~10 per device per 24 h.** Downlinks are scarce because a
  transmitting gateway is half-duplex: it goes deaf to every node's uplinks for the
  downlink's duration. The cap is a gateway-side fair-use limit, not a device limit.
- **Opening RX windows is FUP-free.** The FUP counts transmitted downlinks, not opened
  RX windows. So "always listen, command rarely" costs nothing against the policy.
- **Use unconfirmed uplinks.** A confirmed uplink forces a downlink ACK that burns one
  of the 10/day. We acknowledge a command in the next uplink's telemetry instead.
- EU868 downlink sits in sub-band P (869.4 to 869.65, 500 mW, 10% duty), chosen to give
  gateways ~10x downlink headroom; US915 has no duty limit but a 400 ms dwell cap. Net:
  downlink is scarcer in EU than US, so prefer commanding while over CONUS if we can.

---

## 3. Substantiated against our flight data

Energy reuses the 1 F supercap model in `analysis/power/relay_power_budget.py`
(8.86 J usable, baseline 0.343 J/cycle at SF9/1200 s). Coverage from
`analysis/network/data/receptions.csv` (281 heard uplinks over 291.8 h).

**RX-window power cost: negligible. RX-every-cycle is affordable.**

| Listen budget / cycle | J/cycle | % of 0.343 J baseline | % of 8.86 J cap |
|---|---|---|---|
| 50 ms (typical, empty RX2) | 0.0011 | 0.31% | 0.012% |
| 200 ms (realistic) | 0.0043 | 1.24% | 0.048% |
| 1 s (worst case, full RX2) | 0.0213 | 6.22% | 0.241% |

For comparison the Meshtastic relay-listen is 25.57 J/cycle (2.9x the entire cap); one
relay cycle equals ~6,000 command-RX cycles. The difference is duty: the command
channel listens ~0.02% of the cycle. The one guardrail: cap the RX2 timeout so a
missed decode cannot hang the receiver and walk into the 1 s column.

**Command coverage: only ~9 to 31% of flight-3 was commandable.**

A downlink only reaches us in range of a gateway. Binning the gaps between heard
uplinks: 69% of the flight (200.1 h, the Atlantic leg) had zero gateways, 9% was
continuously tracked, 31% was ever-in-coverage land (CONUS + Iberia). So command
latency is bimodal: average ~10 min over land, up to ~8 days over the ocean. The ocean
case is the radio-independent argument for B2B store-and-forward.

**Throughput / latency:** 10 commands/day max (FUP-bound, not opportunity-bound; 72
RX opportunities/day). In coverage: best ~1-2 s, worst one cadence (~20 min), average
~10 min.

**What we would have toggled mid-flight (evidence-based):**

| Setting | Data | Verdict |
|---|---|---|
| SF7 to SF9 | 281/281 uplinks flew SF7; EU868 RSSI min -129 dBm on the SF7 floor (-124.5); best fresh reach 252 km vs the 412 km horizon | highest single lever, +5 dB, zero hardware |
| GPS reset | 77% of post-launch fixes STALE; 11 wedges, up to 6.9 h of frozen position; needed over the ocean | keystone, but needed where downlink cannot reach |
| Cadence by region | 200 h ocean transmitting was wasted (0 gw); Iberia had gateways | geofence cadence + SF, not a manual toggle |
| Night cadence | battery min 3.322 V = the 3.32 V brownout floor exactly; night median 3.338 V | drop cadence at night; tiers already partly do this |
| Relay enable | continuous RX is 2.9x the cap, browns out in 3.6 min into darkness | keep power + solar gated, never at night (already designed) |

The cross-cutting result: the command channel reaches only 9-31% of the flight, and its
biggest win (the GPS reset) was needed over the ocean where downlink cannot reach. So
it pairs with (a) autonomous geofenced rules on-board for the 69% ocean, and (b) B2B
store-and-forward to carry commands in and telemetry out of the dark leg.

---

## 4. What other flights do (prior art)

- **Dominant pattern: compile-time config, no in-flight downlink reconfig.** lightaprs
  LightTracker (the popular LoRa pico-tracker) sets interval / SF / TX power / region in
  code and reflashes; no RX-window command handling.
- **The one real cautionary tale: Imperial College `picotracker-Lora`.** It opens the
  standard Class-A RX windows (its log shows "RX on freq 923300000 Hz at DR 8",
  confirming our US915 RX2 numbers) but **deliberately defers / ignores in-flight
  channel-change requests** to avoid destabilizing a flying node. A real balloon team
  chose to neuter network-pushed PHY changes on purpose.
- **The clean pattern to copy: LMIC-node.** Its downlink command is a single fixed
  opcode byte on a dedicated application fPort, handled only on TX-complete (strictly
  Class A). Dragino does interval the same way (app-layer opcode + arg, e.g. 01 00 00 5A
  = set interval 90 s). Cadence change is universally app-layer, never a MAC command.
- **Meshtastic remote admin** warns you can "completely drop a node off the mesh if not
  careful" with a bad remote setting. We run a Meshtastic relay, so that lesson transfers.
- **Disable ADR for mobile nodes** is universal guidance; a balloon crossing gateways is
  the textbook case where ADR fights the link. Keep ADR off and do not let TTN drive our
  PHY: our hand-rolled stack ignores MAC commands, so letting the network manage SF /
  RX-params would desync the network's view of our state (a documented brick vector: a
  bad RXParamSetupReq loses the downlink path).

---

## 5. Firmware reuse (most of this already exists)

- **RX windows:** `otaa_join()` already does RX1/RX2 `receive()` with inverted IQ. The
  command receiver is ~80% the same code path as join-accept RX.
- **Persistence:** the `lorawan_session_t` backup-register struct (TAMP, 128 bytes,
  `firmware/include/lorawan.h`) is the natural home for the persisted command state;
  bump its `version` field. TAMP survives reset but not a deep cold boot, so a hard
  power loss correctly reverts to safe defaults.
- **GPS reset:** `gps_ublox_reset()` exists (PIN_GPS_RESET_N). The keystone opcode just
  calls it.
- **SF:** `REGION` is a mutable struct, so `REGION.tx_sf` is already settable at runtime.
- **Crypto:** AES + session keys exist for uplinks; downlink decrypt reuses them with the
  direction bit set to 1.
- **Cadence:** compile-time `#define`s today (`TRANSMIT_INTERVAL_SEC`,
  `SLEEP_INTERVAL_*` via `power_adc_get_sleep_interval_sec`). Needs a small
  runtime-variable refactor to be commandable.
- **No command handling exists yet**, so the dispatcher is greenfield.

---

## 6. Command set: surface these, refuse those

**Worth it (idempotent, bounded, cannot brick):**

| opcode | command | arg | guardrail |
|---|---|---|---|
| 0x01 | set cadence | enum {600, 1200, 1800, 3600 s} | whitelist only; refuse anything faster than 600 s (FUP: SF9 308 ms x uplinks/day must stay < 30 s) |
| 0x02 | relay enable / disable | bool | pure on/off |
| 0x03 | force GPS reset | none | calls `gps_ublox_reset()` |
| 0x04 | safe-mode | none | slowest cadence, GPS-light, relay off (a recoverable panic button) |
| 0x05 | force rejoin | none | re-OTAA to recover a wedged session |
| 0x06 | set SF (constrained) | enum {SF9, SF10} | never SF7/SF8 (drops below the engineered link budget) or SF11/SF12 (FUP-blowing ToA); auto-reverts |
| 0x10 | request data dump | {what, N} | queue last-N sensor samples / acoustic events for uplink |
| 0x7E | easter egg | none | a canned uplink |

**Refuse (keep compile-time only):** arbitrary SF, RX2 freq/DR, channel plan, RX_DELAY.
These are the brick vectors: one bad value loses the downlink path forever, and there
is no reset at altitude. This mirrors what the Imperial pico-tracker team did.

---

## 7. Protocol spec

- **Transport:** LoRaWAN application downlink on fPort 10. Payload
  `[target:2][opcode:1][seq:1][args:0..N]`. `target` = balloon ID (0xFFFF = broadcast)
  so commands are addressable for the B2B hop.
- **Replay-safe:** LoRaWAN AES integrity + frame-counter already block replay; add a
  monotonic `seq` byte and ignore any command with `seq <= last_applied_seq`, so TTN
  queue re-sends / replaces are idempotent.
- **Persistent + fail-safe:** applied state lives in the backup-register struct with a
  magic + version; a corrupt register or a cold boot reverts to safe defaults
  (slow cadence, relay off, SF9). Never resume an exotic state on an unverified boot.
- **Dead-man auto-revert (the key brick-mitigation):** each command stamps a revert
  deadline (e.g. now + 12 h). If no refreshing command arrives, the device auto-reverts
  to the flight baseline (SF9 / 1200 s / relay-as-configured). A bad command can degrade
  the balloon for at most N hours, not the rest of the flight.
- **Acknowledge in the next uplink, not via confirmed-downlink.** Echo
  `last_applied_seq` + current cadence/mode in the telemetry payload. Closed-loop
  confirmation for free, no extra airtime, no spent downlink ACK.
- **RX posture:** RX2-only, every FULL-tier uplink. Prefer RX2 (fixed freq/DR, and
  SF12's long symbols tolerate our millis-frozen timing slop) over RX1. Consider setting
  RX_DELAY to 5 s (Join-Accept RxDelay) for deterministic TX-to-RX reconfig time, and
  open the RX2 window wide to swallow clock error. Gate on FULL tier + not-burst, the
  same as the relay, so we never reconfigure a browning-out balloon.

---

## 8. B2B-awareness (kept in mind from the start)

The command channel only reaches the balloon 9-31% of the time. The 69% ocean leg, and
the fact that the keystone command (GPS reset) is needed over the ocean, force two
companions:
1. **Autonomous geofenced rules on-board** for the ocean: slow cadence + SF9 over
   sparse/ocean longitudes, faster over dense Iberia. The balloon self-tunes where no
   downlink reaches.
2. **B2B store-and-forward.** The `target` field makes commands addressable. A balloon
   that receives a command for another forwards it on the scheduled P2P wake-window; the
   target applies it and acks back through the relayer. Same radio scaffold as the
   proprietary scheduled-P2P mode (doc 04), now carrying commands as well as telemetry.

---

## 9. Build order

1. **Class-A RX2 receiver** (reuse the join RX path) + downlink decrypt + the fPort-10
   parser. FULL-tier-gated, RX2-only.
2. **Runtime-config struct + the safe command set** (cadence, relay, GPS-reset,
   safe-mode, rejoin) + persistence + dead-man revert + uplink-ack. Easter egg for fun.
3. **Autonomous geofenced rules** (the ocean autonomy, since downlink cannot reach it).
4. **B2B relay of commands + telemetry** (the constellation unlock).

Steps 1 and 2 are the near-term feature and reuse most of the existing radio code.
Steps 3 and 4 keep B2B in view the whole way, as agreed.

---

## Sources

- LoRaWAN L2 v1.0.4 (RX delays, MAC CID table, FPending, ADR, RXParam retain rule):
  https://lora-alliance.org/wp-content/uploads/2021/11/LoRaWAN-Link-Layer-Specification-v1.0.4.pdf
- RP002-1.0.3 Regional Parameters (US915/EU868 DR tables, RX1DROffset, RX2 defaults, dwell):
  https://lora-alliance.org/wp-content/uploads/2021/05/RP002-1.0.3-FINAL-1.pdf
- TTN Fair Use (10 downlinks/day, half-duplex, gateway-charged):
  https://www.thethingsnetwork.org/forum/t/fair-use-policy-explained/1300
- TTN duty cycle + EU868 P-band, and regional limitations (TTN EU RX2 = SF9):
  https://www.thethingsnetwork.org/docs/lorawan/duty-cycle/ ,
  https://www.thethingsnetwork.org/docs/lorawan/regional-limitations-of-rf-use/
- TTN ADR (disable for mobile): https://www.thethingsnetwork.org/docs/lorawan/adaptive-data-rate/
- The Things Stack downlink scheduling / queue ops:
  https://www.thethingsindustries.com/docs/integrations/webhooks/scheduling-downlinks/ ,
  https://www.thethingsindustries.com/docs/hardware/devices/configuring-devices/downlink-queue-ops/
- Imperial College picotracker-Lora (real RX1/RX2 log, ignores in-flight channel changes):
  https://github.com/ImperialSpaceSociety/picotracker-Lora
- LMIC-node (canonical downlink-command pattern): https://github.com/lnlp/LMIC-node
- lightaprs LightTracker (compile-time config): https://github.com/lightaprs/LightTracker-1.1
- Meshtastic remote admin (can drop a node off the mesh): https://meshtastic.org/docs/configuration/remote-admin/
- Dragino app-layer interval downlink: https://wiki.dragino.com/xwiki/bin/view/Main/Notes%20for%20TTN/
- ChirpStack RX-param (bad RX2 = downlink lost): https://www.chirpstack.io/network-server/features/rx-parameter-configuration/
