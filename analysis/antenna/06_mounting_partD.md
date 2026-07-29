# Part D — Mounting / hang-tilt

Question (Teddy's): hang the payload so the monopole points STRAIGHT DOWN (antenna
axis vertical, doughnut peak at the horizon) instead of the flown ~20° corner-hang —
does it help? Engine: as-flown PyNEC pattern (down monopole + solar-panel
counterpoise) rotated by hang-tilt τ, spin-averaged (Part B-0), weighted by the
empirical FRESH-float gateway depression distribution (Part A). Code `_tilt.py` +
`A0_mounting.py`, figs `D4`/`D5`, data `mounting_tilt_sweep.csv`. Verbatim (2026-06-01).

## Answer: YES, nadir-down is optimal — but the gain is small
Effective gain toward gateways vs hang tilt (spin- & distribution-weighted):

| antenna | optimum τ | nadir-down (0°) | flown (~20°) | nadir-down **vs flown** |
|---|---|---|---|---|
| **as-flown (monopole+panels)** | **0°** | 0.50 dBi | 0.42 dBi | **+0.08 dB** |
| vertical dipole | **0°** | 1.82 dBi | 1.50 dBi | +0.31 dB |

So the intuition is **correct in direction** — τ=0 (straight-down monopole) is the
peak for every antenna — but the **magnitude is tiny**: ~0.1 dB for the antenna we
actually fly, ~0.3 dB for a dipole. Two reasons it's so small:

1. **The doughnut is broad and flat near its peak.** A vertical antenna's gain is
   within ~0.5 dB of peak across roughly ±25° of the horizon, and the gateways sit a
   median of only 8° below it — already in the flat top. Leaning 20° barely moves the
   gain at those angles.
2. **The payload spins (Part B-0), which averages the tilt out.** Over a yaw rotation
   the tilted doughnut tips *toward* the gateways half the time and *away* the other
   half; the two largely cancel. A tilt only hurts net because of the curvature of the
   pattern, a second-order effect.

## The nuance D5 reveals (why it nearly cancels)
Gain-vs-depression for τ=0 vs τ=20° **cross over** around 25° depression:
- **near the horizon (0–20°, where most gateways are):** nadir-down is higher.
- **steep angles (>25°):** the tilted, spin-averaged pattern is actually *higher*,
  because spinning a tilted doughnut fills in the near-nadir region the untilted
  null leaves empty.
Since the gateway distribution is dominated by near-horizon angles, nadir-down wins
the weighted average — but only just.

## Bonus finding: the as-flown antenna is tilt-TOLERANT
The monopole+panels curve (D4) is much flatter than the dipole's: it loses only
0.08 dB at 20° and 0.46 dB at 45°, vs the dipole's 0.31 / 1.39 dB. The solar panels
broaden the pattern, making it forgiving of mounting angle — so we do NOT need a
precision-leveled hang. This is reassuring for a string-hung 10 g payload that will
never hang perfectly.

## Recommendation
- **Hang nadir-down if it's free to do so** — it's the optimum and costs nothing. In
  practice: attach the string so the monopole axis hangs vertical (see geometry below)
  rather than from a single top corner.
- **But do not over-invest** — the payoff is ~0.1–0.3 dB, ~30× smaller than the SF
  lever (+5 dB from SF9). Mounting is a "nice, free, do-it-right" tweak, not a margin
  driver. If a corner-hang is mechanically simpler/more stable, the ~0.1 dB cost is
  acceptable.
- **Mechanical stability > a few degrees of tilt.** A hang that swings less (lower σ,
  Part B-0 measured ~2.7°) keeps the pattern steady and avoids deep-fade excursions;
  that matters more than nailing τ=0 exactly.

### String geometry to achieve τ≈0
The monopole exits the bottom edge along the board's long axis. To hang that axis
vertical, the string attach point must sit on the **vertical line through the payload
center of mass**, i.e. at the **top edge centered**, not a top *corner*. A corner
attach offsets the CoM-to-attach line from the antenna axis → the ~20° lean we
measured. Options: (a) a two-leg bridle from both top corners meeting above center,
(b) a single attach at top-center, or (c) shift the attach until the CoM (board +
offset panels) hangs the antenna vertical. The panels are offset, so the true
balance point is slightly off the geometric center — a 2-leg bridle is the robust fix.

## Caveats
- Pattern from the as-flown NEC model (panels as conductive grids); real panel
  flexing/zigzag in the photo will perturb the few-tenths-dB result — which is below
  the noise of everything else, so it doesn't change the conclusion.
- Spin assumed uniform in azimuth (Part A reception azimuth supports this). If the
  payload ever locked into a stable non-spinning attitude, tilt would matter more.

## Figures
- `D4_mounting_tilt.png` — effective gain vs hang tilt, as-flown vs dipole.
- `D5_gain_vs_depression.png` — gain vs gateway depression, τ=0 vs τ=20°, with the
  flight gateway distribution overlaid (the "why").
