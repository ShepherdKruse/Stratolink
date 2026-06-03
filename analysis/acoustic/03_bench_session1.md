# Mic bench session 1 - board #2, 2026-06-03

First live J-Link capture session. Board #2 on PSU (VSTOR ~4.66 V), solar panels
attached, no supercap. `env:mic_test` flashed; all data via `mic_bench.py`.
Figures in `figs/AC2_*`, `figs/AC3_*`.

## What we established

1. **Rig works end-to-end on hardware.** Flash -> live J-Link RAM reads -> analyze.
   `seq` advances across reads (core runs free, non-halting reads), `err=0`.
   Silent baseline: `rms_sq ~ 6`, floor adapts to ~3, `event=0`.

2. **Mic frequency response** (`AC2_probe_white12`): white-noise input -> captured
   PSD is **~flat 200 Hz-4 kHz**, rolling off below ~150 Hz. **Confirms infrasound
   (<20 Hz) is out of band** - an audio MEMS mic is the wrong transducer for the
   novel stratospheric infrasound; it's fine for audio-band events (aircraft, etc.).

3. **Decimator penalty, on real hardware** (`AC2_probe_multitone12`): all 4 tones
   (220/880/1760/3300 Hz) recovered; firmware sinc^1 decode sits **~14 dB** above a
   proper sinc^4+DC-block decode in the gaps. **Signal-dependent**: ~14 dB on
   sparse/tonal, ~9 dB on voice, ~-2 dB on white noise (broadband masks it). This
   is why the stratosphere's near-silent, sparse field is the worst case.

4. **Event detector is NOT broken** (`AC3_sweep_1000hz`): descending 1 kHz level
   staircase with a settled floor (3, threshold 48): silence `rms_sq ~ 6`
   (**8x / ~9 dB margin**), **0/13 false positives**, clean monotonic transfer
   curve, events only on loud steps. -> **The flight-1 50% was never a threshold
   bug; something raises the in-flight `rms_sq` floor above the threshold.**

5. **Harvester test - inconclusive without a load** (silent monitor, panels in
   full sun): `rms_sq` stayed ~6, unchanged from dark. Expected: with PSU holding
   VSTOR and **no supercap / negligible load**, the BQ25570 boost charges VSTOR to
   its OV (~5.36 V) once and **idles** - no sustained switching. The realistic
   test needs the **supercap (or a deliberate VSTOR load)** so the boost keeps
   cycling, plus running from solar. **Deferred to next session.** Thermal drift
   in sun remains a parallel candidate (separate by heating just the mic).

6. **Voice captured** (`AC2_probe_ieee_list1_loud`, `..._sibilants_loud`): IEEE/
   Harvard sentences show clean formants/harmonics; sibilants reach the 4.7 kHz
   Nyquist. Note: `say` output is quiet (speech RMS ~ 0.11, high crest factor) -
   we compress/limit to `*_loud.wav` (RMS ~ 0.37) so it drives the mic well above
   the floor. Single 655 ms frames; grab the loudest of N to dodge word gaps.

## Firmware accuracy + change, validated on real data (2026-06-03)

Captured a real dataset (`data/frame_*.npz`: silence + 1 kHz + multitone + white
+ voice) - offline `decode_sinc1` is **bit-exact** to the firmware, so offline
prototyping == firmware. Analyses: `04_mic_accuracy.py` (AC4), `06_precise_audio.py`
(AC6).

**Two independent problems quantified on real captures:**
1. **DC-offset pedestal.** The mic idles at **50.47 %** density, not 50 %, so the
   fixed `PDM_CENTER=160` leaves a **+2.4-count pedestal** -> silence `rms_sq=6` is
   ~93 % DC, ~7 % real AC noise. The pedestal **drifts with temperature** -> a
   second flight false-positive mechanism (alongside the harvester).
2. **Aliased sinc^1 decimation.** Firmware decode noise floor is **+30/+23/+15/-5/-6 dB**
   (silence/tone/multitone/white/voice) above a proper sinc^4+DC-block decode;
   real 1 kHz tone SNR **41 -> 69 dB (+28 dB)**. Worst on sparse/quiet signals = the
   stratosphere. Also a **-3.9 dB** sinc^1 droop at Nyquist.

**CHANGE MADE (production `mic_acoustic.cpp`):** detector now uses the **DC-blocked
variance** of the ones-count (`var = (N*sumones^2-(sumones)^2)/N^2`, x16), seed 16.
Removes the pedestal entirely. Bench-validated (AC5, AC6): tone/silence margin
**28x -> 233x**, **0 false-positives** (even with room/shower noise), floor stable.
Compiles in `env:stratolink` (51 % flash). **Still needs a multi-day soak on the
full firmware before flight** (like the SF9 change) - the test build validated the
identical computation, not the production cycle.

**Deferred (separate, larger change):** proper **sinc^4 decode** for audio fidelity
(+28 dB SNR). Not needed for the 1-bit energy detector; do it when we add
on-device spectral features (the "acoustic fingerprint"). Offline `decode_proper`
already gives precise audio from captured raw PDM.

## Next session (when supercap is on)
- **Definitive harvester test:** supercap on VSTOR, run from solar, lamp on/off ->
  does silent `rms_sq_var` cross threshold and fire? (reproduce 79 % day / 18 % night).
- **Thermal split (cheap, decisive):** warm just the mic (hand/heat-gun) and watch
  the OLD `rms_sq` climb while the NEW `rms_sq_var` stays flat -> directly proves the
  DC block fixes the thermal mechanism.
- **Solar I-V curves** (separate rig: load sweep + current sense - TBD gear).

Board left with `env:mic_test` flashed - reflash `env:stratolink` for normal ops.
