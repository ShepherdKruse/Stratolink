# Part C — Temperature detuning, conductor material, counterpoise

Does the as-flown antenna stay matched and on-frequency when the stratosphere
chills it? Does the enamelled-copper choice matter? Engine: PyNEC MoM on the
as-flown structure (down monopole + solar-panel counterpoise). Code `80_thermal.py`,
figure `C1_thermal_detuning.png`. Numbers verbatim from the run (2026-06-01).

## Temperatures the hardware actually saw (flight telemetry)
- On-board TMP117: flight min **−42.1 °C**, float median −11.3 °C (n=177).
- The external antenna wire sits in the airstream, colder than the insulated
  board → stratospheric ambient ~ **−50 to −60 °C** at 10–12 km. So −50 °C is the
  real design case, not hypothetical.

## Mechanism 1 — thermal contraction (the one people worry about; it's tiny)
Copper CTE α = 16.5 ppm/°C. Cooling +20 → −50 °C (Δ = −70 °C):
- ΔL/L = α·ΔT = **−0.116 %** → the 86.2 mm wire shrinks 0.10 mm → resonance moves
  **UP** by the same fraction.
- Hand calc: +1.04 MHz. NEC sweep (warm-length vs cold-contracted-length):
  resonance **907.9 → 908.7 MHz, +0.8 MHz.** Agreement confirms the model.
- **VSWR at the operating bands barely moves:** US915 1.19 → 1.19; EU868 1.69 → 1.71.

**Conclusion: cold does NOT meaningfully detune a simple wire monopole.** The
antenna's usable bandwidth is tens of MHz; a sub-1-MHz shift is in the noise. This
is a real, useful negative result — temperature robustness is not a design driver
for the wire antenna, so we don't need a temperature-compensating structure.

## Mechanism 2 — enamel coating (a fixed offset, ~T-independent)
The enamel (εr≈3, ~25 µm) loads the wire so its electrical length exceeds physical
→ resonance shifts **down**. Estimated velocity factor **VF ≈ 0.97 (~3 %, ~31 MHz)**.
- This is a ONE-TIME offset you absorb when cutting the wire (cut ~3 % shorter),
  not a drift — and it's nearly temperature-independent (thin coat, field mostly in
  air). Caveat: the exact value needs the King-Wu insulated-antenna integral; our
  estimate sits in the literature 0.95–0.98 band for insulated wire and at the
  high (small-effect) end because our coat is thin. Bare vs enamelled copper differ
  only by this fixed ~3 % length — strip it or just cut shorter; either is fine.

## Mechanism 3 — conductor material
Detuning sensitivity scales with CTE (Δf over −70 °C):
| material | CTE (ppm/°C) | cold shift | note |
|---|---|---|---|
| steel | 12.0 | +0.76 MHz | stiffest, least drift, but lossy/heavy |
| **copper (flown)** | **16.5** | **+1.04 MHz** | best conductor, what we use |
| phosphor-bronze | 17.3 | +1.10 MHz | springy → survives launch/handling, ~Cu loss |
| aluminium | 23.1 | +1.46 MHz | lightest, most drift (still negligible), hard to solder |

All shifts are <1.5 MHz → **material choice is NOT driven by thermal detuning.** It's
driven by mass, solderability, and mechanical survivability. Cold copper also drops
~25 % in resistivity → marginally *higher* efficiency at altitude (a small freebie).

## Material recommendation
- **Keep enamelled copper.** It's the best conductor, the thermal drift is
  negligible, and the enamel both prevents shorting against the PCB/panels and is a
  fixed length offset we already (implicitly) tuned around. Cutting ~3 % short
  compensates the velocity factor.
- If launch/handling bends the wire (a real failure mode for a 10 g payload),
  **phosphor-bronze** is the springy alternative at near-identical RF behavior — a
  mechanical upgrade, not an RF one.
- Aluminium saves mass but is hard to solder to the feed and drifts most; not worth
  it at this scale.

## Incidental finding (feeds Part D / dual-band)
The fixed-length wire's VSWR minimum sits at ~905 MHz: **US915 is near-perfect (1.19)
while EU868 rides up the skirt (~1.7).** A single wire length slightly favors the US
band — a candidate contributor to the Part A US/EU RSSI gap (alongside gateway
density). A length splitting the difference (~tuned to ~886 MHz) would balance both
bands; worth a deliberate choice in v2.

## Caveats
- NEC models bare perfect conductors; the enamel VF is an analytical estimate layered
  on top, not a NEC dielectric solve. The contraction (mechanism 1) IS a true NEC
  result. The qualitative conclusion (cold is negligible) is robust either way.
- Panels modeled as the same conductive grid as Part B; their own thermal expansion
  (Kapton/PET substrate, higher CTE) could shift coupling slightly — second order,
  not modeled.

## Figure
- `C1_thermal_detuning.png` — reactance & VSWR vs frequency, warm vs cold lengths.
