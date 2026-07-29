# Part E — Mechanical stability: pendulum / string dynamics

Teddy: the string was a random length of *elastic* line, not measured. Can we
recover it from the data, and what should v2 use? Code `B0_pendulum.py`, fig `E1`.
Verbatim (2026-06-01).

## Can we measure the string from flight data? Amplitude yes, length NO.
- **String length is NOT recoverable.** Length lives in the pendulum *period*
  (T = 2π√(L_eff/g) ≈ 1–3 s, i.e. 0.3–1 Hz). Telemetry samples every **308 s**, so
  the swing is aliased ~300× — we get random-phase *snapshots*, never the period.
  No amount of cleverness extracts L from 5-minute samples; the physics is degenerate.
- **Swing amplitude IS (weakly) recoverable**, from how far |a| departs from g. The
  only thing that can push the accelerometer *above* g is kinematic (centripetal)
  motion, so the excess a_max/g − 1 bounds the amplitude. Result:
  **swing amplitude ≤ ~8° (upper bound, noise-limited).** The p95 of |a|/g is 0.991 —
  the swing barely lifts |a| above g, so the payload swung **gently**, fully
  consistent with Part B-0's tight (σ≈2.7°) attitude. It did **not** tumble or swing
  wildly. That's the key mechanical finding: the as-flown setup was already stable.

## String length → swing period (the design curve; the bench will pin L)
| L (m) | period fixed-pivot (s) | period balloon-coupled (s) | swing freq (Hz) |
|---|---|---|---|
| 0.3 | 1.10 | 1.05 | 0.95 |
| 0.5 | 1.42 | 1.36 | 0.74 |
| 1.0 | 2.01 | 1.92 | 0.52 |
| 2.0 | 2.84 | 2.71 | 0.37 |
| 3.0 | 3.48 | 3.32 | 0.30 |

The balloon pivot isn't fixed (it's a buoyant 32" sphere with added air mass), which
shortens L_eff slightly (~5%) → period a touch faster than the naive formula. **Longer
string = slower swing = steadier antenna pointing** (and the antenna is tilt-tolerant
anyway, Part D). On the bench (denser sea-level air) the balloon coupling differs from
float — note the direction when comparing a ground swing-test to flight.

## The real risk of an ELASTIC string: parametric resonance
A stretchy line makes a **spring-pendulum**, which can pump energy from vertical
bounce into swing when the **bounce frequency ≈ 2× the swing frequency** (Mathieu
parametric instability). This is the one way a calm payload can spontaneously start
swinging. Danger spring constant k ≈ 4·m·g/L for m = 10.28 g:
| L (m) | avoid k near (N/m) | i.e. a string that sags … under the payload |
|---|---|---|
| 0.5 | 0.81 | ~12 cm |
| 1.0 | 0.40 | ~25 cm |
| 2.0 | 0.20 | ~50 cm |

**Rule of thumb:** if the string visibly stretches/bounces under the 10 g payload and
the bounce looks ~twice the swing rate, you're in the danger zone. **Fix: use a
stiffer (less elastic) line, or detune L so f_bounce ≠ 2·f_swing.** The elastic string
used on flight-3 was a latent risk that happened not to bite (swing stayed ≤8°), but
v2 should not rely on luck — go stiffer.

## Recommendation (preserve the 10.28 g mass — keep the monopole)
1. **Switch to a low-stretch line** (braided Dacron/Spectra, or thin fishing
   monofilament) — removes the parametric-resonance risk at ~zero mass cost. This is
   the highest-value mechanical change.
2. **Length: longer is steadier**, but the antenna is tilt-tolerant (Part D: 0.08 dB
   over 20°) so this is not critical. ~1–1.5 m is a reasonable default: slow enough
   swing (~0.4–0.5 Hz) to keep pointing steady, short enough to not tangle. Avoid
   pathological lengths only via the parametric check above.
3. **Attach at top-center / 2-leg bridle** (Part D) so the monopole hangs ~vertical.
4. **Don't over-optimize** — flight-3 was already mechanically gentle; the wins here
   are insurance (kill the elastic-resonance risk), not margin. The link budget (SF9)
   remains the dominant lever.

## What the bench test should measure (feeds Task 5)
The bench is where we get what the flight data can't:
- **String length ↔ period:** hang the payload on candidate strings, give a small
  push, **video at 60 fps or log accel at ≥50 Hz for 60 s**, FFT → swing frequency →
  L_eff (cross-check vs E2). Confirms our period model.
- **Elastic vs stiff:** repeat with the old elastic line vs a stiff line; watch for
  the bounce↔swing energy transfer (parametric pumping) on the elastic one.
- **Damping:** how many swings to decay — a steadier (more damped) hang holds pointing.

## Caveats
- Amplitude bound is noise-limited; the true swing could be a few degrees either way,
  but is robustly small. A high-rate bench/next-flight accel log would measure it
  directly (and get the period/length).
- Balloon-coupled period uses a first-order added-mass estimate; the bench (in air)
  and float (thin air) bracket the real value.

## Figure
- `E1_pendulum.png` — (left) |a|/g histogram vs swing-amplitude signatures; (right)
  string-length ↔ swing-period design curve.
