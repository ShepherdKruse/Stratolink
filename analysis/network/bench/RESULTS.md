# Meshtastic relay bench, session 1 results (2026-06-03)

stratolink-2 on PSU 4.8 V / 0.8 A (no supercap), J-Link (EDU Mini V2) on the debug
pads, RTL-SDR Blog V4. Firmware: `env:meshtastic_relay_diag` (flashed, auto-cycling).

## Confirmed (real hardware)

| # | Result | Value | Meaning |
| --- | --- | --- | --- |
| **T-init** | `radio_begin_state` | **0** | **Our SX1262 configures for Meshtastic LongFast** (SF11/BW250, sync 0x2B, preamble 16). The keystone unknown, answered YES. |
| **T6** | mode-switch (`msw_us`) | **~1.29 ms** | LoRaWAN↔Meshtastic radio reconfig is negligible, one-radio coexistence is free. |
| **T11** | ToA LongFast vs BW500 (`toa_us`/`bw500_us`) | **473 ms / 237 ms** (32 B) | Measured airtime; BW500 (§15.247-clean) is ~2× faster on air. |
| **T5 (radio side)** | RX vs radio-OFF current @ PSU | both ~**15-16 mA** (Δ < 1 mA at 4.8 V) | The **radio's RX draw is small** (~5 mA at the radio rail reflects to ~1-2 mA at 4.8 V via the SX1262 DC-DC + buck). Listening is cheap. |

**Key insight:** the bench ~15 mA is dominated by **MCU-run + un-slept GPS/sensors**
(the diag never sleeps the MCU/peripherals), **NOT flight-representative**. In flight
those sleep, so relay-listen ≈ radio-RX + STOP-floor.

## T1 + T3 CONFIRMED ON A LIVE MESH (the big result)

There is a **live Meshtastic mesh near the bench** on 906.875 LongFast, and the diag
both **receives and relays** it (mrd read 2026-06-03):

| Metric | Value | Meaning |
| --- | --- | --- |
| `rx_count` | 30→32 (climbing) | **T1: our SX1262 receives real LongFast frames** |
| `last_from` | 0xA2EBC29C, 0xa86802a8, 0x0a3139a5 | multiple **real** mesh node IDs |
| RSSI / SNR | -110 to -114 dBm / -7.75 to -12.5 dB | real far-node signals (deep, plausible) |
| `relay_fwd` | 9 | **T3: forwarded real packets** (hop-1, opaque, **no PSK loaded**) |
| `relay_dedup` | 8 | dedup works (didn't re-forward repeats) |
| `relay_hop0` | 2 | correctly drops hop-exhausted packets |
| `uptime` | 2556→2580 s | running 43 min, `begin=0`, phase cycling RX→TXBEACON |
| `tx_count` | 189→191 | transmitting (steady 15 mA + brief 473 ms TX bursts → looks steady at a glance) |

**This validates the whole thesis end-to-end on real traffic:** a minimal, header-only,
keyless repeater on our flight hardware receives and forwards a real Meshtastic mesh,
deduping and decrementing hop, exactly "just relay what we receive, register nothing."

## Live-mesh + relay characterization (forced RELAY, ~2 min, 2026-06-03)
- **Local mesh is sparse/light:** ~**1 packet/min** received (rx 35→37 / 96 s), bursty;
  **≥5 distinct node IDs** seen; all **weak (-110 to -116 dBm, SNR ≈ -11 dB)**, distant
  neighborhood nodes near our SF11/BW250 floor.
- **Relay on real traffic:** cumulative **fwd=11, dedup=10, hop0=3**, forwards new,
  suppresses repeats, drops hop-exhausted. `dedup ≈ fwd` ⇒ ~half of heard packets were
  already-seen rebroadcasts (managed-flood good-citizen suppression, happening naturally).
- **Model data point:** at ~1 pkt/min the relay's airtime is negligible → the N9
  "sparse ⇒ relay freely, safe" regime, now measured locally. (A dense-mesh saturation
  stress test would need a busier environment.)

## Live-network (MQTT) cross-validation (2026-06-03, 150 s, US LongFast feed)
Subscribed to the public Meshtastic MQTT (mqtt.meshtastic.org, meshdev/large4cats),
decoded ServiceEnvelope headers (no key needed, from/relay_node/rssi are plaintext):
- **1 of our 5 RF-heard local node IDs (`0xa86802a8`) confirmed on MQTT** (via gw
  `!79683c38`) → **our SX1262's RX independently validated against the public network.**
- **4 of 5 local nodes NOT on MQTT → the local mesh is mostly RF-only / off-grid** →
  precisely where a balloon relay adds value (no other path off the island).
- **Our relay marker `relay_node=0xD1`: 3 incidental packets, 0 from our nodes** →
  our forwards aren't observable on MQTT here because local nodes mostly don't bridge.
  (Confirm relay participation via the Heltec bridge, not the public firehose.)
- **US network scale:** 22,362 pkts / 3,075 nodes / 392 gateways in 150 s (~9k/min);
  71% direct (relay_node=0), one relayer carried 16%, relaying is already concentrated.
- Tooling: `uv pip install paho-mqtt meshtastic`; subscribe NARROW (`msh/US/2/e/LongFast/#`),
  not `msh/#` (broker ACL-drops the firehose wildcard).

## Still open
- **SDR off-air isolation of OUR beacons:** band is busy *with the real mesh* + an
  ambient carrier (~+380 kHz) + the RTL-SDR DC spike; coarse waterfall/trigger couldn't
  cleanly separate our 2 dBm beacons. Moot now, the J-Link mrd data is authoritative
  (we RX, TX, and relay). gr-lora_sdr decode would be the way to read frames off-air.
- **J-Link contact:** the Tag-Connect pads drop ("target voltage too low") on long
  hand-held sessions. **Get a TC2030 retaining clip / jig** for stable multi-second
  sessions (the STOP-RX test below needs one). Short snapshot reads (`watch_mrd.sh`)
  tolerate drops better (a drop just skips one tick).

## Pivotal next test, the real relay-listen current

The number that decides power-gated-relay viability is **MCU in STOP + radio in RX +
wake-on-RxDone (`EWRFIRQ`)**, everything asleep except the listening radio. The current
diag runs the MCU flat-out, so it overstates. Build a phase-2 diag that: sleeps GPS +
sensors, enters STOP1, RX-continuous, `EWRFIRQ` set, wakes on RxDone. Expected
relay-listen ≈ STOP-floor (µA, known ~3-5 µA) + radio-RX (~5 mA rail) → **low single-mA**
→ would *beat* the model's 5.5 mA assumption (the radio was never the cost). If the MCU
*can't* wake from STOP on RxDone, relay-listen = ~15 mA and the budget is ~3× worse, so
this binary capability is the make-or-break.

## Other next steps
- **Heltec V3 ×2** (ordered) → real wire-compat (node decodes our frame, T2) + the
  A→relay→B bridge (T3) + RX of real LongFast (T1).
- **Supercap install** → T7 (solar surplus / floor-abort / duty `f`) via cap-decay.
- Step attenuator → T10 sensitivity sweep.
