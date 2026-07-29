# Part B — Antenna pattern modeling (PyNEC method-of-moments)

Models four real candidates at both bands (EU868 / US915) against the Part A flight
geometry and the Part B-0 measured attitude. Engine: PyNEC 1.7.3.4 (NEC2 MoM),
validated to 2.18 dBi / 73-ish Ω on a thin half-wave dipole. Code: `_nec.py`,
`60_patterns.py`. Figures `B1..B3`, scores `data/pattern_scores.csv`.

## Method (what makes this honest, not a textbook citation)
1. **PCB ground plane is the measured 23.4 × 57.3 mm**, modeled as a node-connected
   NEC wire grid (surface patches do NOT reliably bond to a feed wire in NEC — that
   bug produced a spurious −33 dB in a first pass; caught by a length-sweep showing
   the reactance never crossed zero. The grid model resonates correctly).
2. **Effective gain toward gateways** = antenna pattern integrated over the *empirical*
   float depression-angle distribution from Part A (median 8°), averaged over the
   payload's uniform yaw-spin and measured ~20° cant (Part B-0). One number per
   antenna/band — "how well does this serve the flight we actually flew."
3. **Feed mismatch** folded in separately (−10·log10(1−|Γ|²) vs 50 Ω): the monopole's
   real problem.

## Scorecard (verbatim from pattern_scores.csv)
| antenna | band | peak dBi | feed Z (Ω) | VSWR50 | mismatch dB | eff-gain (matched) dBi |
|---|---|---|---|---|---|---|
| **vertical dipole** | EU868 | 2.2 | 85+48j | 2.4 | 0.8 | **+0.6** |
| **vertical dipole** | US915 | 2.2 | 85+48j | 2.4 | 0.8 | **+0.6** |
| horizontal dipole | both | 2.2 | 85+48j | 2.4 | 0.8 | −1.6 |
| turnstile | both | 2.2 | 85+48j | 2.4 | 0.8 | −1.7 |
| **monopole+PCB (flew)** | EU868 | 1.5 | 21−71j | 7.5 | **3.8** | **−2.9** |
| **monopole+PCB (flew)** | US915 | 1.5 | 21−66j | 6.7 | **3.5** | **−2.6** |
| monopole no-GP (bound) | — | 1.8 | 18−3900j | huge | ~36 | −35 (unphysical NEC isolated-wire bound; reference only) |

## Findings
1. **Vertical λ/2 dipole beats the flown monopole+PCB by ~3.4 dB** toward where gateways
   actually were — a large, recoverable margin gain on a link that ran at the SF7 floor.
2. **The monopole's deficit is mostly FEED MISMATCH (~3.5–3.8 dB), not pattern** (raw
   effective gains 0.9 vs 1.5 dBi differ by only ~0.6 dB). The 23×57 mm ground plane
   detunes a nominally-λ/4 wire to Z≈21−j68 (VSWR~7). **Two fix paths:** (a) switch to a
   dipole (no ground plane needed), or (b) keep a monopole but retune length / add an
   L-match for the real ground plane. (a) is simpler and also fixes pattern asymmetry.
3. **Horizontal dipole and turnstile are ~2 dB WORSE than the vertical dipole** for our
   geometry. The HF/WSPR community flies horizontal dipoles, but their links are
   ionospheric/skywave; ours are near-horizon LOS to **vertically-polarized** ground
   gateways, so a vertical radiator wins. This is a case where copying the balloon
   community would have hurt us — substantiation mattered.
4. **Band symmetry:** results are nearly identical at 868 and 915 (a half-wave dipole is
   ~4% off-resonant across that 5% frequency span — negligible). So a single dipole length
   serves both bands; the US/EU RSSI gap from Part A is NOT a dual-band antenna mismatch.
   It is most likely gateway-density/sampling (EU heard us on far more gateways).

## Caveats (carry into Part C/D)
- The no-GP monopole row is an unphysical NEC bound, excluded from plots; the +PCB grid
  model is the trustworthy "what flew."
- B3's vertical-dipole elevation cut is its axial-null plane and under-sells it visually;
  trust the 3D spin-averaged B2 metric, not the 2D cut.
- Patterns assume free space (no balloon/payload dielectric loading, no enamel effect on
  the wire — enamel is thin, ~0.1 dB). Part C handles the −50 °C detuning and materials.
- Polarization is folded in only via the cant+spin geometry; an explicit cross-pol loss
  term for the tumbling-vs-vertical mismatch is a Part C refinement.

## Figures
- `B1_gain_profiles.png` — gain vs depression angle, both bands, gateway band shaded.
- `B2_scorecard.png` — effective gain vs the flown monopole (the decision chart).
- `B3_elevation_polar.png` — elevation patterns, monopole / vertical dipole / turnstile.
