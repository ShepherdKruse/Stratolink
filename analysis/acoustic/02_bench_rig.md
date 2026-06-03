# Mic bench rig - capture, characterize, dial-in

Goal: get the **raw waveform** off the T3902 over J-Link so we design the
acoustic DSP on the laptop against real captures, then port a lean validated
feature back to firmware. Built 2026-06-02; first hardware session = after the
SF9 antenna soak frees board #2.

## Architecture decision - on-device vs off-device (Teddy's question)

**Not either/or - a pipeline.** The two contexts have opposite right answers:

- **In flight (production): the firmware MUST reduce to a compact feature.** The
  bandwidth math forbids raw audio. PCM = 9375 Hz x 16-bit = **150 kbit/s**.
  LoRaWAN at SF9 ~ 308 ms for 35 B, and TTN FUP caps us at ~30 s airtime/day ~
  a few KB/**day** -> we could downlink ~**0.02 s of audio per day**. Raw
  streaming is ~7 orders of magnitude over budget. On-device feature extraction
  is mandatory for flight.
- **In development (now): stream the RAW waveform off-device via J-Link** and do
  the heavy lifting on the laptop. Never trust a 1-bit detector you can't see
  inside (that's how flight-1 shipped a sinc^1 RMS gate with "FFT" comments and a
  50 % coin-flip).

So: **J-Link raw capture -> design/validate DSP + feature on laptop -> distill the
minimal feature into firmware -> re-verify over J-Link -> trust in flight.** The
eventual uplink is an *acoustic fingerprint* (a few FFT-bin magnitudes / band
ratios / a characterized event+level), not a bare bit - designed from data.

## Pieces (all committed)

| file | role |
|---|---|
| `firmware/src/main_mic_test.cpp`, `[env:mic_test]` | self-contained capture build (no LoRa/GPS/IWDG). Fills `pcm_buf` (firmware sinc^1 PCM @9375 Hz) + `pdm_buf` (raw 3 MHz PDM snippet) into RAM; replays the detector into header `mt`. 23.5 KB RAM. |
| `analysis/acoustic/pdm.py` | PDM toolkit: sigma-delta mic model, `decode_sinc1` (firmware) vs `decode_proper` (sinc^4+DC block), PSD/noise-floor helpers. |
| `analysis/acoustic/mic_bench.py` | host harness: `gen / flash / monitor / grab / probe / sim`. |
| `analysis/acoustic/stimuli/*.wav` | sweep, white, pink, click-train, multitone. |
| `figs/AC2_sim_multitone.png` | sim proof: firmware decimator noise floor ~ **+47 dB** worse than proper (validates pipeline w/o hardware). |

RAM symbols (re-derived automatically by the harness via `arm-none-eabi-nm`):
`mt`@0x20000030, `pcm_buf`@0x20002214, `pdm_buf`@0x20000214. J-Link reads are
live/non-halting; firmware bumps `mt.seq` after each frame + dwells 300 ms.

## Tomorrow's procedure (board #2, PSU on VSTOR, panels attached, J-Link SWD)

```bash
cd firmware && ~/.platformio/penv/bin/pio run -e mic_test -t upload   # or: mic_bench.py flash
cd .. && PY=analysis/.venv/bin/python
$PY analysis/acoustic/mic_bench.py monitor          # watch rms_sq / noise_floor / event live
$PY analysis/acoustic/mic_bench.py gen              # (once) make stimuli
$PY analysis/acoustic/mic_bench.py probe analysis/acoustic/stimuli/sweep_log_50_4500.wav
$PY analysis/acoustic/mic_bench.py probe analysis/acoustic/stimuli/multitone.wav
# (turn laptop volume up; speaker near the mic port) -> figs/AC2_probe_*.png
```

Dial-in loop: play stimulus -> `probe` -> read spectrogram 1) vs 2) vs 3) + PSD 4) ->
adjust (level/decoder/threshold) -> repeat. Then talk / play real *sounds*.

### Characterization checklist (what each stimulus buys)
- **sweep** -> frequency response / true passband & roll-off (vs T3902 datasheet).
- **multitone** -> linearity / harmonic distortion / the decimator noise floor.
- **white & pink noise** -> passband shape + how much aliased sum-delta noise the sinc^1
  decode adds (confirm the ~tens-of-dB penalty on the *real* mic).
- **click train** -> transient response + exercises the 55 ms window & the event
  detector (false-positive/again-positive behavior).
- **voice / IEEE-Harvard sentences** -> repeatable intelligibility reference.

### Fold-in tests (cheap, high value)
- **Harvester hypothesis (flight-1 culprit):** shine a lamp on the panels / add
  the supercap so the BQ25570 is actively switching, run `monitor`, watch
  `rms_sq`/`event` track illumination. Scope the `+3.3V` rail ripple. If events
  follow the harvester -> confirmed in situ (matches 79 % day / 18 % night).
- **Thermal split:** cold-soak on clean PSU (foam + dry ice) -> does `rms_sq`
  rise without the harvester? Separates thermal DC-drift from rail noise.

## Settle before mounting optimization
PCM Nyquist = **4.69 kHz**; T3902 is an audio mic. **Infrasound** (meteors,
microbaroms, explosions; <20 Hz) - the genuinely novel stratospheric signal -
is **below** this passband. Decide the target band first (audio events vs
infrasound); an audio MEMS mic may be the wrong transducer for the latter (cf.
NASA/Sandia stratospheric-infrasound balloons w/ dedicated sensors). Mounting
(port orientation, board-vibration isolation, distance from the harvester
inductor) comes *after* the rail-noise + band questions are answered.
