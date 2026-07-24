# Part F: Solar-panel counterpoise, terminal orientation and ground-bond routing

Question (Teddy's, 2026-06-02): the two solar panels are the monopole's counterpoise.
Each panel has a (+) and (-) terminal at **opposite ends**, so one terminal lands near the
board and one lands far. Flight-3 flew **(+) hot near the board, (-) ground at the far edge**,
with the two panel grounds joined by a copper **cross-strap perpendicular to the antenna**
(confirmed from the launch photo). Proposed swap: **(-) ground near the board (~5 mm short
bond), (+) hot on the outer edges**. Would the shorter ground path help, and can we
substantiate it?

Builds on Part D (mounting / hang-tilt). Layers: theory (F1), NEC A/B (done, F2-F5),
flight-data signature (next), bench A/B (the decider).

---

## The reframe: a counterpoise-bonding problem, not a DC-polarity problem

At DC the labels matter (+ to harvester `VIN_DC`, - to board GND). At 905/868 MHz they almost
do not. A solar panel is just a few cm of lossy conductor (cells, tab ribbon, backing). What
the *antenna* sees is (a) how much conductive area is tied to the board RF ground to act as
counterpoise, and (b) the inductance of the wire that ties it there.

So the real design variables hiding inside "which terminal is near the board" are:

1. **Bond inductance.** The panel-to-board-GND wire is a series inductor in the counterpoise
   path. A short bond means low reactance and the panel works as ground plane. A long bond
   means high reactance, the panel is RF-choked off the ground, and the monopole reverts
   toward its (non-radiating) no-ground-plane bound.
2. **Symmetry.** Two short, symmetric L/R ground bonds near the feed give a clean,
   left-right-balanced counterpoise and a smooth omni azimuth (Part A: the spinning payload
   *requires* azimuthal omni). The flown far-edge grounds plus a single cross-strap are
   asymmetric, and the strap carries common-mode current that ripples the azimuth pattern.

Teddy's intuition ("shorter ground path is better") is correct in direction. The reframe says
why and lets us size it. The NEC result below then shows the direction is not the whole story.

## The math (fig F1, `C0_solar.py`)

Series RF reactance of a straight round ground wire, length l, radius a ~ 0.3 mm (skin-effect
/ high-freq form, standard Rosa/Terman result):

    L = (μ0·l / 2π)·[ln(2l/a) - 1]        X = ω·L = 2π·f·L

| bond length | L | X @ 905 MHz | vs antenna |
|---|---|---|---|
| **5 mm (swap)** | 2.5 nH | **14 Ω** | << antenna Z, panel stays bonded |
| 10 mm | 6.4 nH | 36 Ω | comparable to feed R |
| 15 mm | 10.8 nH | 61 Ω | ~ |feed X| |
| **20-30 mm (flown est.)** | 16-26 nH | **88-147 Ω** | > antenna Z, **chokes the panel** |

Put this next to Part B's measured as-flown feed impedance, Z ~ 21 - j68 Ω. A 5 mm bond
(~14 Ω) is small against a ~21 Ω radiation resistance and ~68 Ω reactance, so the panel is
firmly part of the ground. A 20-30 mm path (~90-150 Ω) is larger than the antenna's whole
impedance, so it series-isolates the panel and shrinks the effective counterpoise. Since Part
B already pinned the dominant ~3.5 dB deficit on the too-small ground plane detuning the λ/4
wire, anything that recovers panel-as-counterpoise attacks that exact deficit.

## Why this could be a real lever (unlike hang-tilt)

Part D's hang-tilt payoff was tenths of a dB (the doughnut is flat near the horizon and the
spin averages tilt out). This is different: it does not move the pattern peak, it changes how
much ground plane the monopole has, which Part B showed is worth multiple dB through the feed
match. Best case, fixing the bond recovers a chunk of the 3.5 dB mismatch loss and also cleans
up azimuth ripple (fewer deep fades as it spins). That is a margin-driver-class outcome, if the
model and bench confirm it.

## The honest caveats (why we measure, not just assert)

- **The (+) terminal also bonds to GND at RF**, through the harvester input capacitor (a few
  nF to µF is a near-short at 900 MHz) after the connector and trace. So even the flown panel
  is not fully floating; it is tied via the (+) path through the input cap and the boost
  inductor (which is a high RF impedance in series, the catch). The real improvement from the
  swap depends on how decoupled the panel is *today* via that (+) path, which is a layout
  question NEC and a VNA answer, not algebra.
- **One flight, one config.** Flight-3 data can characterize the problem (is the link pattern
  / orientation / fade-limited? how big is the unexplained RSSI variance?) and bound the prize,
  but it cannot A/B the two wirings. Only the bench on a spare board can.
- F1 is the hypothesis layer. Per the roadmap principle, nothing ships on it alone.

## Substantiation plan

1. **NEC A/B.** Done (`C0_solar.py`, figs F2/F3/F4/F5), see results below. Modeled the ground
   bond explicitly: FLOWN (far-edge + strap) vs SWAP (near-edge short bond) vs bounds (ideal
   bonded / floating), each tuned, swept over panel size. The hypothesis was overturned.
2. **Flight-data signature** (Supabase receptions): quantify the pattern / orientation / fade
   budget. RSSI residual sigma vs the link-budget prediction, multi-gateway simultaneous
   reception spread (same TX instant, different look angles is a live pattern probe), and
   corroborate Part A's n=0.44 flat path-loss. Bounds the achievable prize. Not yet built.
3. **Research**: pico-balloon / cubesat / RF-grounding practice for solar-panel-as-ground-plane
   and counterpoise bonding (BLT, W6MRR/traquito, cubesat antenna notes, EMC strap rules).
4. **Bench A/B** (spare boards #1/#2, feeds into `08_bench_test_plan.md`): the decider. Gold
   standard is a VNA S11 / feed-Z sweep for the two wirings; fallback is a controlled RSSI/SNR
   A/B against a fixed gateway. Ships on our own measurement.

## NEC A/B results: the hypothesis is overturned (substantiated)

`C0_solar.py`, PyNEC NEC2, US915 904.5 MHz. Panels held fixed, only the ground wiring varied.
Delivered effective gain = spin- and gateway-weighted pattern (τ=20°, Part A float depressions)
minus feed mismatch loss. Each config is also tuned (monopole re-cut for best match, because
feed reactance is tunable, per Part B).

| wiring | untuned (λ/4) | **tuned** | tuned Z (Ω) | tuned VSWR | az ripple |
|---|---|---|---|---|---|
| floating (no GND bond) | +0.29 | **+0.63** | 46 - 1j | 1.1 | 0.5° |
| flown (GND to far edge) | +0.22 | **+0.47** | 48 + 2j | 1.1 | 0.5° |
| ideal (fully bonded inner edge) | -0.09 | +0.42 | 41 - 9j | 1.3 | 1.8° |
| **swap (GND to near edge)** | **-4.95** | **-0.03** | 28 + 3j | 1.8 | 1.7° |

1. **Swap is the worst wiring, not the best.** Untuned it craters to -4.95 dBi (VSWR 11.8, the
   λ/4 wire is badly detuned). Even after re-cutting the wire for best match it is still last
   (-0.03), cannot get below VSWR 1.8, and has 3x the azimuth ripple of flown. The "short
   ground path is better" intuition is backwards for this hardware.
2. **Flown was near-optimal; floating is best.** The far-edge / loose ground (flown, +0.47) is
   within ~0.2 dB of the best case, which is to not hard-ground the panels at all (floating,
   +0.63) and let them act as capacitively-coupled parasitic counterpoise.
3. **The big lever is the tunable match (~5 dB), not the bond.** The untuned spread across
   wirings is ~5 dB; tuned it collapses to under 0.7 dB. This echoes Part B: the monopole's
   deficit is feed match, recoverable by re-cutting the wire to the as-built assembly.
4. **Robust to panel size** (F5): `floating >= flown > swap` holds across 0.12-0.33 λ, so the
   sign is not a resonance knife-edge. Spanning that electrical-size range also covers both bands.
5. **Mechanism:** the panels are electrically large (~0.2 λ, comparable to the λ/4 monopole),
   so they are resonant coupled elements, not a passive ground plane. Hard-grounding a
   near-resonant flap right next to the feed yanks the feed impedance (Z ~ 58 + 170j untuned)
   and spoils the omni azimuth. Grounding it far, or not at all, leaves it a gentle
   counterpoise. This is why F1's "bond it tightly with low inductance" premise was the wrong
   model: it assumed a passive ground plane, and the panels are too big for that to hold.

## Revised recommendation (post-NEC; bench decides the magnitude)

- **Do not swap to grounds-near-the-board.** The model says it is the single worst option:
  hardest to match, lowest tuned gain, most azimuth ripple, robust across panel size.
- **Keep the flown far / loose ground, and push it further toward "floating" at RF.** Add a
  series RF choke (ferrite bead, or rely on the boost inductor) on the panel leads so the
  panels look isolated to the antenna, and keep the two panels symmetric for clean omni.
- **Tune the monopole length to the as-built assembly.** The dominant, recoverable lever
  (~5 dB if currently mistuned). Bench S11 sweep, then re-cut.
- **Strongest structural fix: switch to a vertical λ/2 dipole (Part B).** It needs no
  counterpoise, so it sidesteps this entire panel-resonance sensitivity and beats the flown
  monopole by ~3.4 dB. The solar-mounting analysis independently reinforces the Part B "go
  dipole" call.
- **Falsifiable bench prediction:** on a spare, swap shows a worse / shifted S11 (resonance
  pulled well below λ/4, best VSWR above ~1.8) than flown (matches near λ/4). If the VNA shows
  that, the model's sign is confirmed. If not, we learn the unmodeled (+)-via-cap path or the
  dihedral dominates. Either way the bench, not F1, is the decider.

## Caveats on the model (why bench, not model, is final)

Free-space, lossless, coplanar panels (real ones have a dihedral droop, a TODO sweep), no
balloon dielectric, and the (+) terminal's RF path through the harvester input cap is not
modeled (it ties the panel to ground at the other edge to some degree). The untuned sensitivity
is large (~5 dB), so trust the tuned, size-robust ordering (the sign), not the exact dB.
