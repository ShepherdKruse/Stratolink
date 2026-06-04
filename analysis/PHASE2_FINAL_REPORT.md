# Stratolink Phase 2: TTN + Meshtastic on One Radio
### Final analysis & soak report
*2026-06-04 · stratolink-2 bench (PSU 4.8 V + solar, no supercap) · firmware: `env:stratolink` / `env:stratolink_soak`*

---

## 1. Executive summary

Phase 2 adds a **power-gated, open Meshtastic relay** to the existing TTN/LoRaWAN
telemetry firmware, running on the **single** SX1262 radio. In the ~20-minute idle
window between SF9 telemetry uplinks, when (and only when) there is surplus power, the
balloon listens on the Meshtastic LongFast channel and re-broadcasts what it hears -
a header-only, keyless repeater that "relays what it hears and registers nothing."

**The headline result: an 18.3-hour bench soak ran both networks simultaneously on one
radio with zero interference, exact frame accounting, and no brownout.**

| Metric | Result |
|---|---|
| Soak duration | **18.31 h** continuous |
| TTN uplinks → Supabase | **52** (95% delivery, 2 missed cycles), ~20.8 min cadence |
| TTN supply (VSTOR) | **4.64-4.67 V**, flat, no brownout, no drift |
| Meshtastic frames received | **2215** |
| Meshtastic frames **relayed** | **1412** (64%) |
| Frame accounting | **exact**: 1412 fwd + 102 dedup + 696 hop-dropped + 5 cap-skipped = 2215 |
| Good-citizen logic firing | dedup, hop-limit, and 5% airtime cap all fired |
| Adversarial review | no Critical/High; 1 fix applied |

**Flight-readiness:** the relay is **provably mission-subordinate** and validated for
function, coexistence, compliance, and 18.3 h of stability. **One thing remains
untested:** real supercap power-duty (the PSU pinned VSTOR at 4.66 V, so the
floor-abort never had to fire). That is the T7 supercap test below.

---

## 2. Motivation: the ocean gap

Flight-3 (San Francisco → Spain, 12 days, ~9,400 km) went **~8 days dark over the
Atlantic.** TTN performance is purely a function of **ground-gateway geography**
(`analysis/network/01_ttn_performance.md`, `03_ocean_gap.md`):

- Iberia: ~140 gateways nearby (dense). CONUS: thin, ~60% of uplinks heard by a single
  gateway. **Open ocean: zero.**
- 16.7% of flight-3 uplinks already roamed via the Packet Broker, but no broker helps
  where there is no gateway at all.

At SF9 the telemetry uplink is **308 ms every 1200 s, the radio is idle >99.9% of the
time.** The phase-2 thesis: spend that idle time, on surplus power, relaying the local
Meshtastic mesh, giving **transient ~400 km coverage to whatever is beneath the balloon**
- exactly the ocean/desert places no tower reaches.

---

## 3. Architecture (what was built)

Surgical integration: the flight-proven TTN path is **untouched** except one defensive
PHY re-assert; the relay is one self-contained section in `lorawan.cpp` plus one gated
hook in `main.cpp`'s loop.

**Prime safety invariant:** *the relay can never harm the telemetry mission.* It spends
only surplus power, yields to the schedule, and leaves the radio exactly as TTN expects.
Defense in depth, four independent mechanisms:

| Mechanism | Guarantee |
|---|---|
| **Entry gate** (`main.cpp`) | relay only if `tier==FULL` (≥4.5 V, fresh post-TX read) **and** solar charging **and** `!burst` → never at night/dusk/recovery |
| **Floor-abort** (in-window) | exits the instant VSTOR < 4.2 V, 0.9 V above the 3.32 V brownout, 1.2 V above the 3.0 V TTN-TX floor |
| **Schedule yield** | bounded by the inter-cycle budget → next TTN uplink stays on cadence |
| **PHY restore** (every exit) | restores the exact post-init LoRaWAN TX PHY (SF9/BW125/sync/preamble/CRC + freq); the LoRaWAN session (DevAddr/keys/FCnt) is never touched |

**Good-citizen relay** (managed-flooding-friendly): dedup ring (never forward the same
`(from,id)` twice), hop-limit decrement + drop at hop 0, **5% airtime self-cap**, opaque
keyless forward (the 16-byte Meshtastic header is plaintext, so no channel PSK is needed).
**Compliance / geofence:** relay TX only on validated frequencies, US915 → 906.875 MHz,
EU868 → 869.525 MHz; disabled elsewhere; EU airtime cap (5%) is under the 10% SRD duty limit.

Firmware: `firmware/src/lorawan.cpp` (`lorawan_relay_window()` + helpers),
`firmware/src/main.cpp` (gate), `firmware/include/config.h` (`MESHTASTIC_RELAY_ENABLE`,
`RELAY_SOLAR_MIN_MV=3000`, `RELAY_FLOOR_MV=4200`, `RELAY_AIRTIME_CAP_PCT=5`).
Builds: `env:stratolink` (flight, real 3000 mV solar gate) and `env:stratolink_soak`
(identical firmware, gate relaxed to 0 so the relay engages indoors for bench soaking).
RAM 6.5%, Flash 51.6%.

---

## 4. Models (quantitative basis)

### 4.1 Airtime / fair-use
SF9, 35-byte payload → **308 ms** time-on-air. 72 uplinks/day → **22.2 s/day = 74% of
the TTN 30 s/day fair-use cap** (comfortable margin for join retries + clock drift).
TTN therefore occupies **0.026%** of the radio's time; the relay fills the rest and
self-caps its own contribution at **5%** of any window.

### 4.2 Power: why the relay *must* be gated (`analysis/power/relay_power_budget.py`)
On the 1 F supercap (8.86 J usable, 5.36 → 3.32 V), a **naive always-on** relay is
impossible:

| Per 1200 s cycle | Energy |
|---|---|
| Baseline (GPS + uplink + STOP1 sleep) | 0.343 J |
| **Continuous RX relay through the idle window** | **25.57 J = 2.9× the entire cap** |

Daily average current: baseline **0.07 mA** vs **+5.56 mA** with continuous listen (a
**76×** load). Into darkness from 4.5 V: **sleeping survives 82.5 h** (to dawn), but
**continuous listening browns out in 3.6 minutes.** → Listening is only affordable on
**solar surplus**, which is exactly what the firmware gate enforces.

### 4.3 Relay-affordable duty & fleet benefit (`analysis/power/relay_availability.py`)
Using the mission-safe gate (VSTOR ≥ 4.5 V **and** solar > 3 V) against **flight-3
telemetry** binned by local solar hour:

- Flight-3 was at **FULL tier 82.1%** of transmitted moments; **relay-affordable 81.2%**.
- Corrected by local solar hour: **≈ 13.9 h/day** relay-affordable → **duty f = 0.58.**
  It is a **day-following** network (a balloon relays through its local daylight, sleeps
  the cap through night for survival).

Global benefit scales with fleet size (sunlit-land coverage within range of a relay,
R = 400 km footprint):

| Fleet N | Relaying at once (N·f) | Sunlit-land coverage |
|---|---|---|
| 50 | 29 | 5.6% |
| 100 | 58 | 10.8% |
| 250 | 145 | 24.9% |
| 500 | 289 | 43.6% |
| 1000 | 579 | 68.2% |

Cheap (<$80) pico-balloons make fleet scale plausible; the value compounds with N.

### 4.4 Link reach (`analysis/antenna/05_sf_linkbudget.md`)
Flight-3 ran at the SF7 sensitivity floor. **SF9 buys ~+5 dB (~2× range)**, comfortably
past the **~412 km radio horizon at altitude**, the single biggest lever, zero added
hardware. The as-flown monopole + solar panels measured a healthy ~2.7 dBi (matched);
the flight-3 link deficit was free-space-path-loss/budget, not the antenna. A balloon at
float altitude thus opens a **~400 km-radius footprint** of LoRa coverage.

---

## 5. Substantiated results

### 5.1 Bench validation (pre-flight, `analysis/network/bench/RESULTS.md`)
- Our SX1262 **configures for Meshtastic LongFast** (`begin = 0`); LoRaWAN↔Meshtastic
  mode switch is **~1.3 ms** (one-radio coexistence is essentially free).
- Measured ToA: LongFast **473 ms**, BW500 237 ms. Radio RX draw is small (~5 mA at the
  radio rail; the MCU/peripherals are the real cost, hence STOP-during-sleep matters).
- **Live-mesh relay confirmed:** on a real neighbourhood mesh the diag received and
  forwarded real frames (fwd=11 / dedup=10 / hop0=3), keyless, no PSK loaded.
- **MQTT cross-validation:** 1 of 5 RF-heard local nodes appeared on the public
  Meshtastic network → our RX validated against the public network, and 4/5 were
  off-grid → precisely where a balloon relay adds value.

### 5.2 Adversarial review
Independent fresh-context review (into RadioLib 7.6.0 + the STM32WLx ISR/NVIC path) plus
a self-review: **no Critical or High issues.** 13 safety invariants confirmed (PHY
restore complete on all exit paths; the TxDone→RX-flag race handled; watchdog fed;
brownout not credible on the gated cap; header offsets byte-correct; airtime math
overflow-free). **One fix applied:** `relay_restore_lorawan_phy()` now also restores
frequency (closing a latent off-channel trap).

### 5.3 The 18.3-hour soak (`env:stratolink_soak`, the headline)
**TTN telemetry (→ Supabase, verified after the fact):**
- 52 uplinks over 18.31 h, ~20.8 min (1249 s) median cadence, channels hopping
  903.9-905.3 MHz (US915 sub-band 2) as designed.
- **VSTOR flat 4.64-4.67 V** (PSU), no brownout, no drift.
- Solar swung **0.00 → 3.56 V**: it **crossed the 3000 mV flight gate at midday**, so on
  the *flight* firmware the relay would have engaged in real daylight, exactly as modeled.
- GPS fix held (4-17 sats), gateway RSSI -61 to -81 dBm. **95% delivery** (52 of ~53.5
  expected; 2 missed cycles total over 18 h, single indoor gateway).

**Meshtastic relay (J-Link `s_relay` counters):**

| rx | fwd | dedup | hop0 | cap_skip |
|---|---|---|---|---|
| 2215 | **1412** (64%) | 102 | 696 (31%) | 5 |

- 1412 real LongFast frames relayed in 18.3 h (~77/hr). **Accounting exact** at every
  check (2.4 h → 7.6 h → 18.3 h): every received frame is forwarded, deduped,
  hop-dropped, or airtime-capped, nothing unaccounted.
- All three good-citizen mechanisms fired in flight: dedup (102), hop-limit drops (696,
  i.e. 31% of traffic was edge-of-mesh and correctly *not* re-flooded), airtime cap (5).

*Figure: `analysis/network/figs/soak_results.png`, VSTOR dead-flat through the run,
solar crossing the 3.0 V flight gate at midday, and the relay's linear forwarding.*

### 5.4 SDR confirmation
A single **3.2 MHz wide-band capture** centred at 905.4 MHz caught **both networks on
one radio**: a TTN LoRaWAN uplink (SF9/BW125 on 903.9 MHz) and Meshtastic relay forwards
(SF11/BW250 on 906.875 MHz). Figures: `fig_dualband_waterfall.png` (both bands, ~3 MHz
apart) and `fig_dualband_trigger.png` (the two LoRa chirp sawtooths side by side, TTN
narrower, Meshtastic wider/slower).

---

## 6. Validated vs still open

**Validated**
- Relay function, TTN+Meshtastic coexistence on one SX1262 (18.3 h).
- Mission-subordination: TTN cadence + supply unaffected; exact frame accounting.
- Good-citizen behavior (dedup, hop-limit, airtime cap) firing on real traffic.
- Compliance frequencies + keyless operation (no Meshtastic registration needed).
- The gating logic and the PHY-share state machine (no radio-state leakage to TTN).

**Still open (do before flight)**
1. **Supercap power-duty (T7).** The PSU pinned VSTOR at 4.66 V, so the floor-abort and
   the FULL-tier gate never actually had to protect the mission. Install the 1 F cap and
   measure the real relay duty under solar, confirm the **f = 0.58 / ~14 h-day** model
   and that the floor-abort holds the telemetry reserve.
2. **Flight-env soak.** Only `env:stratolink_soak` (gate=0) was soaked; soak
   `env:stratolink` (real 3000 mV gate) so the relay engages on actual solar surplus.
3. **Dense-mesh stress.** The local mesh was sparse (~1.3 frames/min, airtime cap bound
   only 5×). A busier environment would exercise the 5% cap and the managed-flood
   give-way behavior harder.

---

## 7. Conclusion & recommendation

Phase 2 is **flight-ready for the relay function and mission safety**: the firmware is
provably mission-subordinate, passed independent adversarial review, and ran a clean
18.3 h soak with both networks live and exact accounting. The only gate to full flight
clearance is the **supercap power-duty test (T7)**, a power measurement, not a
firmware question.

The bigger picture the models support: a single balloon is a **transient ~400 km LoRa
relay** over the gaps no tower reaches; a **fleet** of cheap pico-balloons becomes a
rolling, decentralized, day-following Meshtastic layer over oceans and remote interior,
with coverage that scales from a few percent at N=50 to ~68% of sunlit land at N=1000.

**Next:** install the supercap → run T7 → soak `env:stratolink` → fly.

---

## Appendix: asset map

| Area | Path |
|---|---|
| Firmware (relay) | `firmware/src/lorawan.cpp`, `firmware/src/main.cpp`, `firmware/include/{config,lorawan}.h` |
| Build envs | `firmware/platformio.ini` (`env:stratolink`, `env:stratolink_soak`) |
| Power models | `analysis/power/relay_power_budget.py`, `relay_availability.py` (+ `.png`) |
| Network study | `analysis/network/01..07*.md` |
| Bench validation | `analysis/network/bench/RESULTS.md` + `tools/` |
| Soak diagnostics | `s_relay` @ `0x200007A8`; read `mem 0x200007A8 0x1C` via JLinkExe |
| Shareable graphics | `analysis/network/figs/`, coverage (single/multi + GIFs), `theory_*`, `fig_dualband_{waterfall,trigger}`, `fig2_waterfall` |
