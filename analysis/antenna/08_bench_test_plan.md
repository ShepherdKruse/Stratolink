# Bench-test plan — stratolink-2 (validate the antenna study on hardware)

Goal: confirm, on real hardware, the firmware-only wins the study identified — **SF9
+ slower cadence** (the +5 dB lever), the **as-flown monopole+panels match**, and the
**string/swing** mechanical choices — *before* committing them to a flight. Board:
**stratolink-2** (the GPS-test board). Keep the monopole (preserve 10.28 g).

Principle (same as the whole program): **no change ships on a citation — it ships on
our own logged measurement.** Each test below has a clear PASS criterion.

---

## Pre-flight: what the study predicts (so the bench can confirm/refute)
| quantity | model prediction | source |
|---|---|---|
| SF7 sensitivity | −124.5 dBm | 05_sf_linkbudget |
| SF9 sensitivity | −129.5 dBm (+5 dB vs SF7) | 05_sf_linkbudget |
| SF7 ToA (35 B) | 97.5 ms | _link.py |
| SF9 ToA | 308 ms | _link.py |
| as-flown monopole+panels | VSWR ~1.7 (Z 54−j21), peak 2.7 dBi | 03_patterns_partB |
| cold detuning | <1 MHz, VSWR unchanged | 04_thermal |
| swing amplitude (flight) | ≤ ~8°, gentle | 07_pendulum |

---

## Test 1 — SF sweep: verify the sensitivity gain is real (the headline)
**Why:** the SF9 recommendation rests on +2.5 dB/step from Semtech's table. Confirm
the *relative* RSSI/SNR margin improvement on our actual radio + payload.

**Setup:** stratolink-2 transmitting the real 35-B telemetry payload; a gateway
(your `onethreenine` TTN gateway, creds in `firmware/test/.ttn_keys`) receiving.
Reuse `firmware/test/ttn_listener.py` (MQTT, already decodes the payload + logs
gateway RSSI/SNR) or `analysis/diagnostics/bench_gps_monitor.py` for the Supabase side.

**Procedure:**
1. Firmware: add a debug build that steps `tx_sf` through 7→8→9→10, N uplinks each
   (or flash per-SF). Log per-uplink RSSI/SNR from `ttn_listener.py`.
2. Hold geometry fixed (board and gateway taped down, same spot) so only SF varies.
3. To probe the *floor*, attenuate: add distance, or a step attenuator on the gateway,
   or transmit from a far/obstructed spot until SF7 just drops out.

**PASS:** SNR margin improves ~+2.5 dB per SF step (±1 dB); SF9/SF10 still decode where
SF7 fails. Records the real sensitivity floor vs the −124.5/−129.5 dBm prediction.

**Watch:** TTN FUP — at SF10/11 keep the test short (few uplinks); you're way over
30 s/day cadence-wise but it's a brief bench run, not a 24 h soak.

---

## Test 2 — Antenna match: NanoVNA on the real structure
**Why:** Part B says the panels act as a counterpoise giving a good match (VSWR ~1.7);
Part C says it's near-perfect at US915, rides up at EU868. Measure it.

**Setup:** NanoVNA (calibrated SOL at the feed plane), connected at the monopole feed
**with the solar panels attached and in flight position** (they're part of the antenna!).

**Procedure:**
1. Sweep 820–960 MHz. Record VSWR/S11 at 868.1 and 904.5 MHz.
2. Note the resonant dip frequency. Compare to the model: dip should sit ~905 MHz,
   US915 VSWR < ~1.5, EU868 ~1.7.
3. **Panel test:** measure with panels, then fold/remove them → confirm the match
   *degrades* without panels (validates the counterpoise finding).
4. **Length/band-balance:** if you want both bands equal, trim toward a dip at ~886
   MHz (Part C) and re-measure.
5. **Cold check (optional):** chill the antenna (freezer/dry ice ~−40 °C), re-sweep →
   confirm <1 MHz shift (Part C prediction).

**PASS:** VSWR with panels materially better than without; dip near 905 MHz; both bands
usably matched (<2:1). Refutes/confirms the "panels = counterpoise" model directly.

---

## Test 3 — String / swing: measure what the flight data couldn't
**Why:** flight telemetry (308 s sampling) can't see the swing period/string length
(Part E). The bench can, with a high-rate log.

**Setup:** hang the payload (or a mass dummy) on candidate strings from a fixed point.

**Procedure:**
1. **Period→length:** small push, record **accel at ≥50 Hz for 60 s** (a debug build
   streaming LIS2DH12 over serial/J-Link) or **video at 60 fps**. FFT the swing → freq
   → L_eff. Cross-check vs the E2 curve (1 m ≈ 0.5 Hz).
2. **Elastic vs stiff:** repeat with the old elastic line and a stiff line (Dacron/
   mono). On the elastic one, deliberately bounce it vertically and watch for swing
   building up (parametric pumping, Part E danger zone).
3. **Damping:** count swings to decay for each line.

**PASS:** stiff line shows no bounce→swing energy transfer and faster decay; pick the
length giving a slow (~0.4–0.5 Hz), well-damped swing. Confirms the Part E model and
picks the v2 line.

---

## Test 4 — (carry-over) GPS stale-fix fix
The original reason stratolink-2 is on the bench. Not antenna-related, but while the
board is out: confirm the GPS fix (foil-block → NOGPS not STALE) per
`firmware/GPS_TEST_PLAN.md` + `bench_gps_monitor.py`. Keep these tests independent
(don't let a GPS debug build mask the SF/antenna runs).

---

## Sequence for this evening (efficient order)
1. **NanoVNA sweep (Test 2)** first — fastest, no firmware change, immediately
   confirms/refutes the antenna model. ~15 min.
2. **String/swing (Test 3)** — mechanical, parallelizable while firmware builds.
3. **SF sweep (Test 1)** — needs a firmware build; the headline link-budget validation.
4. GPS (Test 4) if time.

## What to capture
Log everything to `captures/bench-YYYYMMDD/`: NanoVNA .s1p touchstone files, the
RSSI/SNR-vs-SF table, the accel/video swing recordings. We'll plot Test 1 against the
D2/D3 predictions and Test 2 against the C1 VSWR curve to close the loop.

## Decision gates (what each test unlocks)
- Test 1 PASS → commit **SF9 @ ~900 s cadence** to firmware (the big win).
- Test 2 PASS → keep monopole+panels as-is (or trim to 886 MHz for band balance).
- Test 3 → pick the v2 string (stiff, ~1–1.5 m).
