# Acoustic-event audit - flight-1 (Stratolink-3, 2026-05-17->29)

Roadmap item #4. Question (Teddy): the `acoustic_event` bit fired on ~30 % of
flight-1 cycles on an **untested threshold** - is it real stratospheric
acoustics, payload self-noise, **LoRa-TX coupling**, or a detector artifact?

Method: `analysis/acoustic/01_flight_audit.py` -> `figs/AC1_flight_audit.png`.
Sources: `analysis/antenna/data/telemetry_raw.csv` (flight, n=457) +
`analysis/acoustic/data/bench_stratolink2.csv` (bench, n=570, incl. the
2026-06-02 SF9 soak), pulled from Supabase. Detector = 1 bit/cycle.

## TL;DR verdict

**It is almost certainly board self-noise from the solar power harvester, not
acoustics and not the LoRa radio.**

- **Bench-silent, flight-noisy.** Clean PSU bench = **0.4 %** (2/570). In flight
  = **50 %** (129/256). The "~30 %" headline was diluting these two regimes
  (plus ~3.5 % on pre-launch garbage rows).
- **Flat across altitude / region / link.** In flight the rate is ~50 % from
  0.5 km to 10 km, US~EU, and is **uncorrelated** with RSSI, SNR, `lora_sf`,
  pressure, and the **accelerometer** (|r|<0.1 each, in-flight). So it is *not*
  altitude-graded real acoustics, *not* the link/SF, *not* bulk vibration.
- **It tracks the sun.** In flight: **79 % in daylight** (solar >= 5.02 V, n=87)
  vs **18 % at night** (solar <= 4.95 V, n=85). With the bench (no harvester) at
  0.4 %, the ladder is **0.4 % (no harvester) -> 18 % (harvester idle, on cap) ->
  79 % (harvester actively charging)**.
- **The radio is exonerated by construction.** `main.cpp` reads the mic
  (`mic_acoustic_detect`, L164) ~1 s **before** the LoRaWAN uplink keys up
  (`lorawan_send_uplink`, L193), then sleeps 20 min. A packet's own TX happens
  *after* its acoustic bit is already latched, and TX power/SF don't correlate
  with the bit. Same-cycle RF coupling is impossible; cross-cycle is 20 min away.

Leading cause: **BQ25570 / solar-harvester switching noise coupling onto the
mic's `+3.3V` rail** (the mic `MK1` pad 5 = `+3.3V`, a rail it plausibly shares
with the rest of the board). **Thermal drift is confounded with daylight and
not yet excluded** - warmer mic ASIC in sun could also shift the PDM DC offset.

## Why the detector trips so easily (firmware DSP, the math)

`firmware/src/mic_acoustic.cpp` is a broadband RMS energy gate - **no FFT**
(despite the `telemetry.h` / migration comments). Four weaknesses make it a
near-coin-flip once any rail/quantization noise is present:

1. **Single-stage sinc^1 decimator.** It counts ones over 320 PDM bits and
   subtracts a fixed 160 -> a length-320 boxcar (1st-order CIC), first null at
   3 MHz/320 = 9.375 kHz, **-13 dB** first sidelobe. PDM sum-delta pushes quantization
   noise to *high* frequency by design; a sinc^1 doesn't roll it off, so HF
   shaped noise **aliases** into the 0-4.7 kHz output and inflates `rms_sq`.
   A real PDM front-end uses sinc^4/^5 or an FIR.
2. **No DC block.** Subtracting a *fixed* `PDM_CENTER=160` assumes the mic idles
   at exactly 50 % ones. Any real DC offset delta adds delta^2 to *every* sample -> a
   constant energy pedestal, and that offset drifts with temperature. (No
   high-pass after decimation.)
3. **Starved adaptive floor.** `noise_floor_sq` updates by 1/16 of the residual
   from **one 55 ms sample per 20 min**, only when `rms_sq < 2xfloor`. It needs
   ~16 samples (~5 h) to converge and **resets to the seed (64) on every
   reboot** (NVIC reset on TX-fail/brown-out/watchdog/freefall - frequent in
   flight). So the "adaptive" floor is effectively pinned/miscalibrated.
4. **Threshold = 4x RMS (16x MS).** With the floor pinned low and `rms_sq`
   carrying aliased quantization + a DC pedestal + any rail ripple, the trip
   becomes a coin flip whose rate rises with rail noise (-> the day/night split).

## Hardware proximity (for the EMI picture / v2 layout)

All front-copper (mm): mic `MK1` (56.1, 54.9), radio `U2` RAK3172 (72.7, 64.7),
antennas `AE1` (68.4, 82.7) & `AE2` (62.9, 33.2). -> mic<->radio ~ **19 mm**,
mic<->nearest-antenna ~ **23 mm** (~0.06 lambda at 900 MHz). Close, but the radio is
off during the mic window so this matters only for v2 layout, not the flight-1
events. Mic nets: pad1=`PDM`(->PB4), pad4=`Net-(MK1-CLK)`(->PB3), pad5=`+3.3V`,
pad2/3=`GND`. **Confirm whether `+3.3V` is shared with the harvester output and
whether there's any RC/ferrite isolation on the mic supply (there appears to be
none).**

## Ranked hypotheses & how to kill/confirm each (bench)

| # | hypothesis | flight evidence | bench test |
|---|---|---|---|
| 1 | **Harvester switching noise on +3.3V** | 79 % day / 18 % night / 0.4 % bench; flat vs everything else | run a board on **supercap+solar**, lamp **on vs off**; scope `+3.3V` ripple; log `rms_sq`. If AE tracks illumination -> confirmed |
| 2 | Thermal DC-offset drift of the mic | warm(day)->more; cold bin (-40,-20] only 9 % | **cold-soak on clean PSU** (foam+dry ice); if AE rises cold-independent of solar -> thermal contributes |
| 3 | Aero/wind/balloon self-noise | flight>>bench; but flat vs accel (accel = LF only) | airflow/fan on the mic port at bench; compare spectrogram |
| 4 | Noise-floor collapse in silence | flat ~50 %, floor starved by design | log `noise_floor_sq` + `rms_sq`; replay the EMA offline |
| 5 | ~~Own LoRa TX RF/rail coupling~~ | **ruled out** (mic before TX; flat vs RSSI/SF) | (n/a) key TX during a mic capture on the bench to bound worst-case |

## Next: the bench rig (also unblocks the spectrogram / IEEE-sentence work)

The 1-bit telemetry can't prove a mechanism or do spectral work - we need the
**waveform**. Two capture paths (do both):

- **Saleae PDM capture** (no firmware change): record PB3 (3 MHz clock) + PB4
  (PDM data) at >=12 MS/s; decode PDM->PCM offline with a *proper* sinc^4 decimator
  in Python; FFT/spectrogram. We already use Saleae (`captures/`).
- **Firmware raw-PCM build** (`main_mic_test.cpp`): stream the 9.375 kHz PCM +
  `rms_sq` + `noise_floor_sq` over J-Link RTT for calibrated, repeatable runs.

Then the dial-in loop Teddy described: play known stimuli through a speaker,
capture, compare spectrograms, iterate. Stimulus battery (we care about *sounds*
>= voice): **sine sweeps** (frequency response / passband), **pink + white noise**
(passband shape + decimation artifacts), **transients/claps** (event detector +
the 55 ms window), a few **IEEE/Harvard sentences** (repeatable intelligibility
reference), and target **sounds** (aircraft, etc.).

**Band reality check to settle first:** PCM rate 9.375 kHz -> **Nyquist 4.7 kHz**,
and the T3902 is an audio mic (~100 Hz-10 kHz). The most interesting
stratospheric acoustics - **infrasound** (meteors, explosions, microbaroms,
< 20 Hz) - sit **below** this mic's passband. Decide what we're actually trying
to hear before optimizing mounting; an audio MEMS mic may be the wrong
transducer for infrasound (cf. NASA/Sandia stratospheric-infrasound balloons,
which fly dedicated infrasound sensors).

## Recommended firmware changes (after the bench confirms mechanism)

- Sample the mic **multiple short windows** and report a richer statistic
  (median/percentile of `rms_sq`, or a few FFT-bin magnitudes - the "acoustic
  fingerprint" already noted in the roadmap), not 1 bit.
- Proper **sinc^4 decimation + DC block**; persist/seed `noise_floor_sq` across
  sleep (it survives STOP) and **don't reset it** on NVIC resets.
- Take the mic capture in a **harvester-quiet window** (or add RC/ferrite on the
  mic `+3.3V`) and re-measure - if events drop, mechanism #1 is confirmed in situ.
