# GPS Stale-Fix — Diagnosis & Bench Test Plan (board #2)

Goal: understand *why* the GPS froze in flight when it ran fine for days on the
desk, reproduce it on the bench **rigorously** (not by luck), fix it, and prove
the fix — all on stratolink-2 powered from a PSU (VSTOR + GND), wire monopole,
no supercap/solar yet.

---

## 1. What actually went wrong (diagnosis)

### The mechanism (confirmed in code)
`gps_ublox_get_fix()` ([src/gps_ublox.cpp](src/gps_ublox.cpp)) polls like this:

```c
while (millis() < deadline) {
    gnss.checkUblox();              // pump UART parser
    fill_fix_from_gnss(&last_fix);  // read CACHED accessors
    if (last_fix.valid) { *fix = last_fix; return true; }  // returns on cache
    delay(100);
}
```

`fill_fix_from_gnss()` reads `getLatitude()/getGnssFixOk()/getSIV()` — all of
which return values from the SparkFun library's **last cached UBX-NAV-PVT**, held
in MCU RAM. `getGnssFixOk()` tells you the *last* PVT had its fix-OK bit set; it
does **not** tell you the PVT is *fresh*. So the very first poll after a wake reads
the pre-sleep PVT (fixOK still true, old lat/lon) and returns it as a valid fix —
**before the module has produced a new solution**. Smoking gun from flight data:
`gps_satellites` frozen at 32 and lat/lon/alt/speed/heading bit-identical across
many cycles while pressure/temperature kept changing.

### Why it passed days of desk testing but failed in flight
This is the important part — and it's why a naive re-run won't reproduce it:

1. **Stationary hides it.** On the desk the payload doesn't move, so the stale
   fix *equals* the true position. The bug is invisible — re-reporting the last
   fix gives the right answer. The instant the payload moves between fixes
   (flight), the stale fix is wrong and you get frozen coordinates.
2. **Continuous PSU power = always hot-start.** V_BCKP (3 µA backup domain)
   stays powered on the desk, so ephemeris is retained and every wake is a
   ~5 s hot-start — a fresh PVT lands well inside the 30 s window. In flight,
   low-energy episodes (Flight 3 reported a false ~3.32 V dropout plateau; the
   actual rail/BOR was unobservable) can drop the backup domain →
   ephemeris lost → **30 s cold-start**, which is exactly the firmware's
   timeout (`GPS_COLDSTART_TIME_S = 30`, `timeout_ms = 30000`). Marginal.
3. **Cold + motion + weak signal** at altitude (−40 °C TCXO drift, swinging
   monopole, jet-stream motion) push TTFF past 30 s → no fresh PVT → firmware
   falls back to the stale cache and reports it valid.

Net: the firmware can't distinguish "fresh fix" from "last known fix," and every
flight condition that slows re-acquisition turns that into chronic staleness.
Flight-1 result: **77 % of fixes stale** (216 STALE / 39 FRESH / 26 NOGPS).

### Corollary that drives the test design
A plain PSU/desk soak (stationary, warm, continuous power) **will not naturally
reproduce the bug** — same reason it passed before. We must (a) **instrument the
GPS to detect staleness directly** (independent of position), and (b)
**deliberately induce** the slow-/failed-reacquire conditions.

---

## 2. Hardware under test
- **Board:** stratolink-2, headers → PSU on **VSTOR** and **GND**. Set PSU to a
  representative VSTOR (e.g. 3.6–4.0 V "FULL" tier; later sweep down toward the
  conservative 3.32 V reported-plateau accounting floor; sweep below it to
  actual BOR with independent VSTOR/VOUT capture). Current-limit ~150 mA.
- **PSU:** Siglent **SPD1000X** — SCPI-scriptable over USB/LAN (Python + pyvisa or
  raw socket): `OUTP CH1,OFF` / `OUTP CH1,ON` on a schedule, or step `CH1:VOLT`
  down to simulate sag. We use this to automate brownout/cold-start cycles (P3).
  (May also have a built-in Timer/list mode worth checking in the menu.)
- **Antenna:** wire monopole (soldered). Note length/feed for the record.
- **GPS:** u-blox MAX-M10S, UART1 @ 9600 (PB6/PB7), **reset on PA0** (active-low),
  also on **I²C 0x42** (unused alt path). AIRBORNE_4G dyn-model applied on wake.
- **No supercap / solar** yet — add later only for the brownout-interaction phase.
- **Log transport:** **LoRa → TTN → Supabase** (primary; see §3) — board runs free
  on PSU, J-Link only to flash. RTT/UART reserved for the optional wired cold sweep.

---

## 3. Test transport & detection — decided: **LoRa → TTN → Supabase**
We do **not** tether J-Link for the soak (it needs a laptop and you have to move
it). The board runs free on the PSU and reports over its real radio path: LoRa →
your **apartment TTN indoor gateway** → webhook → Supabase. J-Link only flashes.
We pull the logged rows with our analysis scripts (creds in `~/.config/stratolink/env`).

**Detection needs no web/payload changes.** The fix changes *behavior* in a way the
existing Supabase columns already capture — deny the GPS (foil / power-cycle) and:
- current firmware → rows keep a **frozen but "valid" position** (STALE), `sats` stuck;
- fixed firmware → rows go **NOGPS** (`lat` null, `sats` 0).
Stationary is fine: the signal under test is *stale-vs-null*, not position change.
We extend `analysis/diagnostics/gps_stale_audit.py` to classify the bench rows.

*Optional richer path (later, only if needed):* a `main_gps_test.cpp` build that
streams CSV over J-Link RTT for a wired session, logging the freshness signals the
production code ignores:

| field | source | why |
|---|---|---|
| `ms` | `millis()` | timeline |
| `wake_n` | counter | cycle index |
| `itow` | `gnss.getTimeOfWeek()` | **PVT freshness — frozen iTOW = stale** |
| `getPVT_fresh` | `gnss.getPVT()` returns true | did a NEW PVT arrive this poll? |
| `fixType` | `gnss.getFixType()` | 0=none,2=2D,**3=3D** |
| `gnssFixOK` | `gnss.getGnssFixOk()` | the flag the prod code (wrongly) trusts |
| `siv` | `gnss.getSIV()` | sats; 32-frozen was the flight tell |
| `lat,lon,alt` | cached | position |
| `ttff_ms` | measured wake→first-fresh-PVT | re-acquisition cost |
| `vstor_mv` | ADC | power context |

This lets us **measure the bug rate on a stationary bench**: if `gnssFixOK==1`
but `itow` hasn't advanced since last cycle, that's a stale fix the production
firmware would have transmitted as valid. Plot stale-rate vs condition.

---

## 4. Test phases (run in order)
All observed via Supabase unless noted. Board on the table by your TTN gateway.

**P0 — Baseline soak, current firmware, good signal (multi-day).** Antenna in the
clear. Expectation: near-all FRESH, consistent rows. Confirms "desk works" + a
clean control. (Stationary → STALE is invisible here; expected.)

**P1 — Reproduce the bug: current firmware + foil.** Tinfoil over the GPS antenna.
Expectation: rows keep reporting the **frozen last position as valid** with `sats`
stuck — the bug, caught at system level in Supabase even while stationary.

**P2 — Apply the fix, repeat the foil test.** Expectation: rows go **NOGPS** (`lat`
null) within ~1 cycle of covering the antenna; resume FRESH within ~1 cycle of
uncovering. The binary before/after proof.

**P3 — Brownout / cold-start induction (Siglent SCPI cycling).** Script the
SPD1000X output off→on (and/or ramp below the V_BCKP retention threshold) to force
ephemeris loss → 30 s cold-start. Expectation (fixed fw): long TTFF correctly
flagged NOGPS, not stale; PA0 reset recovery un-sticks a wedged module. Add the
**supercap here** for the realistic V_BCKP decay curve (not needed earlier — the
PSU gives cleaner control).

**P4 — Multi-day fixed-firmware soak.** Leave it running several days, occasionally
toggling foil. Confirm **zero** "frozen-position-as-valid" rows in Supabase.

**P5 — Motion (car drive, later).** Roommate's car + AC-outlet PSU, drive a few
hours. Confirms FRESH fixes track real movement and no stale creeps back — the one
thing a stationary test physically can't cover.

**Cold (optional, separate):** a metal fridge/freezer is a Faraday cage — it blocks
the LoRa uplink too, so we can't observe via TTN from inside one. For a cold sweep,
use a **foam cooler + dry ice** (RF-transparent, ≈−78 °C) so telemetry still gets
out, or run a short wired J-Link/RTT session for cold only.

---

## 5. The fix (apply after P0–P4 characterize the failure)
In `gps_ublox_get_fix()`:
1. **Freshness gate.** Use `gnss.getPVT()` (returns true only on a *new* PVT) as
   the poll trigger; accept only if `fixType >= 3 && SIV >= 4 && itow advanced`.
   Stop trusting cached `getGnssFixOk()` alone.
2. **NOGPS on timeout, never stale.** On no fresh valid PVT within the window,
   `valid=false`; `main.cpp` must send a **NOGPS sentinel** (not the last fix —
   today it falls back to `gps_ublox_get_last_fix`). Confirm webhook maps the
   sentinel → null lat/lon.
3. **Recovery.** After N consecutive non-fresh cycles, pulse **PA0 reset** to
   warm-restart the module (keeps V_BCKP/ephemeris → ~5 s), then grant extra
   acquisition time. Escalate to a UBX cold-start if reset doesn't recover.
4. **Fix-age.** Track seconds/cycles since last fresh fix (feeds the v2 payload
   discussion + lets the ground distinguish stale from fresh).

**Re-run P0–P4.** Success criteria:
- P0/P1: fresh fixes still reported when truly available.
- P2 (foil): **NOGPS within 1 cycle** (was: stale-as-valid).
- P3/P4: longer TTFF correctly flagged NOGPS, not stale; PA0 recovery un-sticks.
- Zero Supabase rows with a frozen-but-"valid" position under GPS denial (every
  denied cycle becomes NOGPS / null lat, never a repeated stale position).

---

## 6. Prior art to review (then substantiate on our hardware)
- u-blox MAX-M10S **Integration Manual** + UBX **interface description**: NAV-PVT
  `iTOW` / `valid` flags / `fixType`, power-save (PMREQ) wake→TTFF behavior,
  backup-mode ephemeris retention.
- SparkFun u-blox v3 library: `getPVT()` vs auto-PVT vs cached-getter semantics.
- HAB community (UKHAS / pico-balloon): power-save vs continuous GPS at altitude,
  AssistNow / AssistNow-Offline ephemeris to cut cold-start TTFF.
Each becomes a logged, plotted result on stratolink-2 — not just a citation.
