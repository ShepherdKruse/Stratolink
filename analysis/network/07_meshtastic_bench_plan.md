# Meshtastic relay, bench test plan

Goal: amass the data to **substantiate or refute every model and decision** from the
network study (docs 01-06) before we write a line of flight firmware. Each test maps
to a specific claim + the analysis script it feeds. Run on a spare Stratolink board
(RAK3172) over J-Link, with the existing power-capture rig.

**Bench courtesy / compliance:** develop on a **private channel** (custom name → its own
frequency slot, off the default LongFast mesh) at **minimum TX power**, and watch our own
emissions on the **SDR**. Do real-mesh interop checks (T2/T3 on default LongFast) only
briefly and low-power, once the logic works. (No shield box on hand, private-channel +
low-power + SDR-monitor is the substitute.)

## Traceability matrix, claim → test → pass criterion

| Claim / model (doc) | Test | Pass criterion |
| --- | --- | --- |
| SX1262 can RX/TX Meshtastic LongFast wire-format (04) | T1, T2 | decode a stock node's packet; stock node decodes ours |
| Header-only opaque relay, **no PSK** (06, §3) | **T3** | 3rd stock node receives our forwarded packet, hop-1, we hold no key |
| Managed-flood: dedup + ROUTER_LATE cancel/late-window (N10) | T4 | no double-forward of one id; defers when it hears a prior rebroadcast |
| Relay-listen current 5.5 vs ~10 mA; EWRFIRQ wake-on-RxDone (relay_power_budget) | **T5** | measured mA; wake-from-STOP-on-RxDone works |
| Mode-switch cost negligible + LoRaWAN survives (04) | T6 | swap < ~5 ms; TTN uplink OK after N swaps |
| Solar surplus supports relay; floor-abort; f≈0.58 (relay_availability) | **T7** | cap stays ≥ floor under relay in "sun"; relay auto-suspends in "dark" |
| TTN keeps priority; no missed uplinks (04 scheduler) | T8 | 0 missed/late TTN cycles over ≥50 cycles with relay active |
| AirUtilTX ≤7.5% / ChUtil cap / EU 10% (N9, 06) | T9 | measured AirUtilTX ≤ cap under load; never exceeds EU 10% |
| Sensitivity → ~200 km practical / 410 km LOS footprint (N8) | T10 | measured LongFast sensitivity ≈ -131 dBm; RSSI vs attenuation curve |
| BW250 (interop, gray) vs BW500 (clean §15.247) (06 #1) | T11 | BW500 does NOT interop w/ default LongFast; airtime delta measured |

## Equipment / prerequisites (tailored to current bench, 2026-06-02)

- **Boards:** 2× Stratolink (RAK3172) total, but **both currently tied up** -
  `stratolink-2` is mid GPS-soak on the bench; `stratolink-1` is with Caleb (CO) until
  **Sunday**. Board-based tests begin when the soak frees #2 or #1 returns. The
  power/coexistence tests (T5/T6/T7/T8) need only **one** board + J-Link.
- **Measurement = J-Link / RTT only** (per preference, no external power rig in the loop):
  power via the **1 F supercap as a coulomb counter**, I = C·dV/dt from the on-board
  VSTOR ADC, logged over RTT. The **Saleae Logic MSO** is used **once** to calibrate the
  dV/dt→mA slope (the VSTOR ADC reads a few % low, see `power_adc.cpp`), then set aside.
  This is the same energy-reference method as `analysis/power/gps_start_power.py`.
- **Reference Meshtastic node:** **none yet, order one, ideally two.** Recommended:
  **2× Heltec V3** (ESP32-S3 + SX1262, ~$20, USB-C, OLED), cheap, web-flashable, gives
  the bench bridge *and* a balcony base; or a **RAK WisBlock RAK4631** (nRF52, lower
  power) for a permanent solar base. Needed for interop/bridge (Phases A/B/D); power tests
  don't need it.
- **SDR (on hand):** observe our TX off-air, watch channel utilization, verify LongFast
  frames, covers the RF-observation role and part of T10.
- **TTN indoor gateway (on hand):** the uplink receiver for **T8**, confirm our LoRaWAN
  telemetry still reaches it on schedule while the relay runs in the gaps.
- **Attenuator:** none on hand → the **T10 sensitivity sweep is deferred** (or order a
  cheap USB step attenuator, ~$15-30); meanwhile use SDR + RSSI-of-received as a proxy.
- **Node emulator (when a 2nd board frees):** a Stratolink running a "ground node
  emulator" build that TXes crafted LongFast packets with known id/hop/rate, for
  deterministic load (T4, T9) and dedup tests without a stock node.
- **Harvester loop (T7):** BQ25570 + 1 F supercap (C5) + the solar panel + a lamp/cover -
  or a sunny windowsill, to drive light/dark cycles.

## Instrumentation / harness to build

1. **`meshtastic_relay_diag` PlatformIO env** (mirrors the `gps_diag` pattern): puts the
   RAK3172 into Meshtastic-LongFast mode via RadioLib, runs the relay loop, and logs a
   `mrd` struct over J-Link/RTT, RX packet (RSSI/SNR/len/header fields), relay decision
   (forward / dedup-drop / hop=0-drop / late-cancel), mode-switch timing, VSTOR/solar.
   Core config + loop (from the verified wire spec):

   ```cpp
   // --- enter Meshtastic LongFast mode (US slot 19 = 906.875; EU = 869.525) ---
   radio.standby();
   radio.setFrequency(REGION_MESH_FREQ);
   radio.setSpreadingFactor(11); radio.setBandwidth(250.0); radio.setCodingRate(5);
   radio.setPreambleLength(16);  radio.setSyncWord(0x2B);   radio.setCRC(true);
   radio.startReceive();
   // --- relay loop on RxDone (header offsets: to[0..3] from[4..7] id[8..11]
   //     flags[12] channel[13] next_hop[14] relay_node[15]) ---
   if (len < 16) return;                       // not a valid frame
   uint8_t hop = buf[12] & 0x07; if (!hop) return;        // hop exhausted
   uint32_t id = u32(buf+8), from = u32(buf+4);
   if (seen(from,id)) return;                  // dedup ring
   mark_seen(from,id);
   buf[12] = (buf[12] & ~0x07) | (hop-1);      // decrement hop_limit
   // ROUTER_LATE: wait the late window in RX; cancel if (from,id) reheard
   if (!reheard_during_late_window(from,id)) radio.transmit(buf, len);  // opaque, no decrypt
   radio.startReceive();
   ```

2. **Node-emulator env** (2nd board): crafts/sends LongFast frames with set id/hop/rate.
3. **`analysis/network/bench/`**, a logger that ingests RTT/serial + power-rig captures
   into per-test CSVs, and analysis scripts that **feed the existing models**:
   T5/T7 → `relay_power_budget.py` + `relay_availability.py`; T9 → `91_open_relay.py`;
   T10 → `90_meshtastic_relay.py`; so bench numbers replace the datasheet assumptions.

## The tests

### Phase A, Wire compatibility (does our radio speak Meshtastic?)
- **T1, RX a real LongFast packet.** Config as above; place a stock node nearby on the
  same (private test) channel; confirm we receive frames, CRC-valid, and correctly parse
  the 16-byte header (to/from/id/flags/hop/channel). *Data:* count, RSSI, SNR, parsed
  fields. *Pass:* ≥95% of the stock node's TX decoded; header fields sane.
- **T2, TX / be heard.** Transmit a crafted LongFast packet; confirm the stock node /
  Meshtastic app shows it. *Pass:* stock node receives + displays.

### Phase B, The relay (core feasibility)
- **T3, Header-only opaque forward, NO PSK (the keystone test).** Topology: node A and
  node C placed out of direct range (attenuate/separate); relay board between. A sends a
  message; relay forwards (hop-1, payload untouched, *no channel key loaded*); confirm C
  receives it. *Data:* end-to-end delivery, hop decrement, latency. *Pass:* C receives
  A's message **only** via the relay, with the relay holding no PSK. This proves the
  whole "just relay what we receive" thesis (doc 06 §3).
- **T4, Dedup + ROUTER_LATE.** Drive duplicate ids (emulator) and a competing
  rebroadcaster; confirm (a) no id forwarded twice, (b) relay defers/cancels when it
  hears a prior rebroadcast (late window). *Data:* forward/cancel log, measured
  contention delay (~28 ms slot @ LongFast). *Pass:* dedup 100%; late-window cancel works.

### Phase C, Power (the gating constraint)
- **T5, Relay-listen current (the key power number).** On **stratolink-2 as it is now**
  (stiff 4.8 V PSU rail, NO supercap): the diag holds each radio state for ~20 s
  (`SLEEP`/`STANDBY`/`RX`/`TXBEACON`), so just **read the PSU current display per
  labelled phase**; relay-listen current ≈ `RX` - `STANDBY`. *Pass:* `RX` adds ≈ the
  ~5.5 mA the model assumes; flag if it's the ~10 mA (MCU-must-run) case. **Feeds
  `relay_power_budget.py`.** *(Once the supercap is installed, switch to the cap-decay
  method I = C·dV/dt from VSTOR over J-Link, same as `gps_start_power.py`. The MCU-
  STOP + `EWRFIRQ` wake-on-RxDone optimization is a phase-2 diag.)*
- **T6, Mode-switch cost.** Time + energy of LoRaWAN→Meshtastic→LoRaWAN reconfigure;
  run ≥100 swaps then a real TTN join+uplink. *Pass:* swap < ~5 ms; TTN uplink succeeds
  after swaps (no BUSY/DIO wedge). Validates coexistence overhead (doc 04).
- **T7, Solar surplus + floor-abort + duty (validates f≈0.58).** On the BQ25570/1F/
  solar loop, cycle the lamp (bright→dim→dark) with the relay listening; log VSTOR,
  solar, relay-on/off. *Data:* surplus current at cap-clamp; hours-equivalent the relay
  can sustain; does floor-abort fire before brownout? *Pass:* cap holds ≥ floor while
  relaying in "sun"; relay auto-suspends as VSTOR drops (no brownout). **Feeds
  `relay_availability.py`, replaces the telemetry-inferred f with a measured surplus.**

### Phase D, Coexistence + good citizen
- **T8, TTN priority / preemption.** Run the integrated loop (TTN cycle every 1200 s +
  relay in the gaps) for ≥50 cycles; confirm every TTN uplink fires on schedule and the
  relay yields the radio. *Data:* TTN uplink timestamps vs schedule; missed/late count.
  *Pass:* 0 missed, 0 late beyond margin.
- **T9, AirUtilTX / ChUtil cap (validates N9).** Drive a synthetic packet load
  (emulator at rising rate); confirm the relay's own AirUtilTX stays ≤7.5% and it backs
  off as ChUtil rises; verify EU-region build never exceeds 10% duty. *Data:* AirUtilTX
  & ChUtil vs offered load. *Pass:* cap holds; matches the N9 self-throttle curve.

### Phase E, Range / link
- **T10, LongFast sensitivity + RSSI vs attenuation (validates N8 footprint).** With a
  step attenuator, find the RX sensitivity floor and the RSSI/SNR vs path-loss curve on
  our hardware + antenna. *Data:* sensitivity (dBm), RSSI vs attenuation. *Pass:*
  sensitivity ≈ -131 dBm (LongFast); curve consistent with the ~200 km practical / 410 km
  LOS model. (True air-to-ground range = a later **field/altitude test**, noted below.)

### Phase F, Compliance data
- **T11, BW250 vs BW500 A/B (validates doc 06 decision #1).** Run the relay at LongFast
  (BW250) and at a BW500 preset; confirm BW500 does **not** interoperate with default
  LongFast nodes (different slot), and measure the airtime/energy delta. *Data:* interop
  yes/no each; ToA + TX energy each. *Pass:* clean data to make the interop-vs-§15.247
  call deliberately.

## Out of bench scope → field tests (note for later)
- **Real air-to-ground range** (the 200 km/410 km footprint) needs altitude, a tethered/
  short HAB or a high-site test, logging RSSI vs distance from a moving ground node.
- **Real-mesh ChUtil over a populated area** (saturation behavior), only meaningful in
  the field; until then T9's emulator load is the proxy.

## Sequencing (given current board/node availability)
**Now, no free board, no node:** order the Meshtastic node(s); build the harness
(`meshtastic_relay_diag` firmware, node-emulator build, `bench/` logger) so it's
**flash-ready**; finalize this plan. No RF work yet.

**First runnable, one board + J-Link (+ TTN gateway), no Meshtastic node needed:**
**T5 → T6 → T7 → T8** (relay-listen current, mode-switch, solar/floor-abort, TTN-priority).
These validate the *power budget and coexistence*, the gating questions, and need only
a single Stratolink + J-Link + the on-bench TTN gateway. Runnable as soon as the GPS soak
frees `stratolink-2` (or `stratolink-1` returns Sunday).

**When a node arrives + a board is free:** **T1 → T2 → T3** (the header-only bridge, the
keystone) **→ T4 → T9 → T11**. T3's full A→relay→B bridge wants 2 stock nodes, or 1 stock
node + the 2nd board as the emulator. **T10** (sensitivity sweep) only if a step
attenuator shows up; otherwise SDR + RSSI-of-received as a proxy.

## Data → model loop
Every test writes a CSV under `analysis/network/bench/<test>/`; the analysis scripts
re-run with measured values so the models (power budget, availability f, N8/N9 curves)
become *bench-substantiated* rather than datasheet-assumed. Update docs 04/05/06 with the
measured numbers and flag any model that the bench refutes.
