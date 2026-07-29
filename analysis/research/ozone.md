# Ozone Retrieval from Stratolink-3 UV Telemetry — Implementation Plan

> Research output from sub-agent investigation. Headline science output from flight #1: invert broadband LTR390 UV measurements during ascent to recover a vertical ozone profile, anchored absolutely against TROPOMI/OMI overpasses.

## 1. Retrieval math (Beer-Lambert in altitude form)

Monochromatic Beer-Lambert for direct solar UV at altitude `z`:

```
I(z, λ) = I_TOA(λ) · exp[ −σ(λ,T) · SCD(z, SZA) ]
```

- `I_TOA(λ)` [photons s⁻¹ cm⁻² nm⁻¹] — top-of-atmosphere solar irradiance (TSIS-1 HSRS).
- `σ(λ,T)` [cm² molec⁻¹] — temperature-dependent ozone cross section.
- `SCD(z, SZA)` [molec cm⁻²] — slant column density of O₃ above altitude `z`:
  `SCD = AMF(SZA, z) · VCD(z)`, with vertical column `VCD(z) = ∫_{z}^{TOA} n_{O3}(z') dz'`.
- Chapman/secant-corrected airmass for our altitudes (12–20 km, SZA ≤ ~80°): `AMF ≈ 1/cos(SZA_eff)` is acceptable; for SZA > 75° use the Chapman function `Ch(χ,R/H)` with `R≈6371 km`, scale height `H≈30 km` for ozone, which avoids the secant blow-up. Reference Smith & Smith 1972 / Kivalov & Fishman.

We measure broadband current that maps to `uv_index = raw/2300` (uint8). The forward model integrates:

```
S = ∫ I_TOA(λ) · R(λ) · exp[ −σ(λ,T_eff) · SCD ] dλ
```

where `R(λ)` is the LTR390 normalized spectral response (280–430 nm, peak ~320 nm). For a single broadband detector, retrieve the **column above the balloon** by inverting `S(z) → VCD(z)`. The **profile** comes from differentiating successive ascent samples:

```
n_{O3}(z̄) ≈ −[VCD(z₂) − VCD(z₁)] / (z₂ − z₁)
```

with `z̄ = (z₁+z₂)/2`. This is the classic in-situ differential UV photometer technique used by the NASA-JSC balloon photometer (Robbins, Carnes, Hipskind 1983) and NOAA dual-beam ozone monitors — except here we have only one channel and no internal scrubber, so the unknown is `VCD(z)` rather than local mixing ratio.

## 2. Effective absorption cross-section `σ_eff`

Define a band-averaged effective cross-section weighted by the system response and the TOA solar spectrum:

```
σ_eff(T, SCD) = − (1/SCD) · ln[ ∫ I_TOA(λ) R(λ) e^{−σ(λ,T)·SCD} dλ / ∫ I_TOA(λ) R(λ) dλ ]
```

This is **mildly SCD-dependent** (broadband cross-section ambiguity — see §6). Pre-compute a lookup table `σ_eff(T, SCD)` at 5 K and 50 DU steps for inversion.

Inputs:
- LTR390-UV-01 spectral response `R(λ)` digitized from LITE-ON datasheet Fig. 4 (peak ~320 nm, FWHM ~50 nm, drops below 10% at <290 nm and >360 nm).
- Ozone cross-sections: **Serdyuchenko et al. 2014** (AMT 7, 625) covering 213–1100 nm, 0.02–0.24 nm, at 11 temperatures 193–293 K, parametrized `σ(T) = σ₀(1 + c₁t + c₂t²)`, `t = T−273.15`. WMO/IO3C replaced Bass-Paur with these in 2016. Files: <https://www.iup.uni-bremen.de/gruppen/molspec/databases/index.html>.
- Solar TOA: **TSIS-1 HSRS** (Coddington et al. 2021, GRL) at 0.001–0.01 nm, 0.3% uncertainty 460–2365 nm, 1.3% elsewhere — use 280–430 nm slice. <https://doi.org/10.1029/2020GL091709>; data via LASP LISIRD.

Approximate magnitude: at 320 nm and 293 K, σ ≈ 4.0×10⁻¹⁹ cm² molec⁻¹; at 325 nm, the BIPM photometric reference value is σ = 1.647×10⁻²⁰ cm² (Janssen et al. 2018, AMT 11, 1707). Integrating Serdyuchenko · R(λ) · I_TOA over the LTR390 passband should yield **σ_eff ≈ (1.0–1.5) × 10⁻¹⁹ cm² molec⁻¹** at T_eff ≈ 230 K (stratospheric). One DU = 2.69×10¹⁶ molec cm⁻², so a 300 DU overhead column gives slant optical depth at SZA=30°: τ ≈ σ_eff · SCD ≈ 1.2×10⁻¹⁹ · 8.07×10¹⁸ · sec(30°) ≈ 1.12 — comfortably in the sensitive (non-saturated) regime.

## 3. State-of-the-art context

- **NASA-JSC balloon UV photometer** (Patterson, Robbins; Springer 1985) — dual-cell with scrubber, profiles 25–35 km.
- **NOAA dual-beam ozone photometer** (Proffitt & McLaughlin 1983) — gold standard for airborne in-situ. UCAR/ACOM: <https://www.acom.ucar.edu/start/O3noaa_description.pdf>.
- **Brewer/Dobson Umkehr** — ground-based, exploits SZA-varying scattered UV. Mateer & Deluisi 1992 (UMK92); Petropavlovskikh et al. 2005 GRL.
- **Ozonesondes (ECC, Brewer-Mast)** — wet-chemistry, ~5% accurate, NDACC standard.
- **Satellite (OMI OMTO3, TROPOMI O3_TOT_HiR, OMPS)** — total column reference, validation against Brewer/Dobson typically ±2–5%.
- **Amateur / picoballoon UV-ozone**: essentially nothing published. Picoballoon literature (Ruthroff) is APRS-tracking-focused, not science. HASP student ozone payloads (LSU) and CalPoly TomBaker have flown UV photodiodes but with multichannel filters. **The Stratolink approach — single broadband UV + satellite anchoring on an amateur platform — appears to be a novel data product.** This is publishable as a methods note in AMT or HamSCI.

## 4. Solar zenith angle library

Recommendation: **`pvlib.solarposition.spa_python`** (NREL SPA, Reda & Andreas 2008, ±0.0003°). It exceeds our needs by 4 orders of magnitude.

- `pysolar` — fine accuracy (~0.1°) but slower-moving project, limited refraction handling.
- `astropy.coordinates.get_sun` + `AltAz` — heavier dependency, requires IERS tables, overkill.

Edge cases:
- **Refraction** at high SZA: at our altitudes (>12 km) atmospheric refraction is ~1/3 of surface value; for SZA<85° ignore, for SZA>85° apply Bennett 1982 formula scaled by pressure ratio.
- **Earth curvature**: replace plane-parallel `sec(SZA)` with Chapman function above SZA 75°.
- **Twilight (SZA > 90°)**: retrieval invalid — sun is below the local horizon. Filter rows where `SZA > 85°`.
- Use `astropy.time.Time` only for ISO8601 parsing; pass UTC datetimes to pvlib.

## 5. Absolute DU anchoring (OMI / TROPOMI overpass collocation)

**Products** (in order of preference):

1. **TROPOMI S5P_L2__O3_TOT_HiR V2** — 5.5 × 3.5 km resolution, GODFIT direct-fitting algorithm. NRT version `S5P_L2__O3_TOT_HiR_NRT` available within 3 hours. Access: GES DISC + Copernicus Data Space (S5P-PAL). <https://disc.gsfc.nasa.gov/datasets/S5P_L2__O3_TOT_HiR_2/summary>.
2. **OMI OMTO3 V003** — 13 × 24 km nadir, TOMS v8.5 algorithm using 317.5/331.2 nm pair. <https://disc.gsfc.nasa.gov/datasets/OMTO3_003/summary>. Daily L3 `OMTO3e` on 0.25° grid for backup.
3. **OMPS-NPP/NOAA-21 NMTO3-L2** — continuity, lower resolution.

**Collocation window**: spatial ±50 km from balloon ground track, temporal ±3 hours. Tighten to ±25 km / ±1 h when float is stable. TROPOMI offers one overpass per day at mid-latitudes (~13:30 LT); chain with OMI (~13:45 LT) when available for cross-check.

**Access**: `earthaccess` Python package with NASA Earthdata Login token. For Sentinel-5P also via Copernicus Data Space `sentinelsat` or new `cdsetool`. Cache HDF-EOS5 / netCDF files locally; compute area-weighted mean total column from pixels within window.

**Anchor algorithm**: let `Ô₃_sat` be the collocated satellite total column. Our retrieved column-above-balloon `VCD_balloon(z=0)` (extrapolated to surface using a climatological tropospheric column from `OMI O3_TROP` or McPeters/Labow climatology, ~30 DU) plus ground-to-balloon integral should equal `Ô₃_sat`. Fit a single multiplicative calibration `k` per overpass: `VCD_corr = k · VCD_raw`. Track `k` over flight; drifts >5% suggest sensor degradation or aerosol contamination.

## 6. Error budget

| Source | Magnitude | Notes |
|---|---|---|
| **Quantization** (uv_index uint8, `raw/2300`) | **±5–8%** dominant at low signal | Worst contributor. Future boards must report 20-bit raw. |
| Cross-section temperature | ±2% at 320 nm between 220 K and 250 K | Use ERA5 or onboard pressure→T mapping |
| Broadband σ_eff ambiguity | ±3–5% | Mitigated by SCD-dependent LUT |
| Cosine response | ±5–10% | LTR390 has bare-die diffuser, poor cosine. Flag SZA > 60° as suspect. |
| Cloud/aerosol below balloon | ±2% above floats >15 km, ±10% in ascent through clouds | Use ambient_lux as cloud proxy |
| SZA / time | <0.1% | Negligible |
| Solar UV variability | ±1% at 300 nm over solar cycle | TSIS-1 HSRS includes 2018 epoch; scale by Mg II index if needed |
| Absolute anchor (satellite) | ±3–5% | TROPOMI vs Brewer bias |

**Realistic total uncertainty**: **±10–15% for column above float (>15 km), ±20–30% for ascent profile bins.** Publishable as semi-quantitative; not competitive with ozonesonde precision.

## 7. Pitfalls and failure modes

- **Low-altitude ascent (<8 km)**: thick cloud layers, multiple scattering breaks direct-beam assumption. Mark as "transit", do not invert.
- **Twilight (SZA > 85°)**: long path, refraction matters, scattered light dominates. Drop.
- **Polar vortex edge / ozone hole**: T_eff drops to 190 K, σ shifts. Use ERA5 vertical T profile, not single-T LUT.
- **Specular reflection from cloud tops or solar panel glint** on the balloon itself: detect via correlation between `solar_voltage` spikes and `uv_index` spikes; flag and drop.
- **Aerosol layers** (Asian dust, volcanic SO₂/sulfate): need OMI AAI as exclusion mask.
- **Saturation**: uv_index=255 at raw≈586,500 — at our latitudes only plausible above 25 km in summer. Flag as out-of-range, switch to extrapolation.
- **Pressure-only altitude on NOGPS rows**: use US Standard Atmosphere 1976 inversion `z = z_0 - H·ln(p/p_0)` per layer; tag uncertainty.

## 8. Code architecture under `analysis/ozone/`

```
analysis/ozone/
├── __init__.py
├── data_loader.py        # Pull telemetry from Supabase / capture CSVs; clean nulls
├── altitude.py           # Pressure -> altitude (US Std Atm 1976 layered)
├── sza.py                # Wraps pvlib SPA; refraction; AMF (secant + Chapman)
├── cross_section.py      # Loads Serdyuchenko nc files; σ(λ,T); σ_eff LUT builder
├── solar_spectrum.py     # Loads TSIS-1 HSRS; resamples to 0.1 nm grid
├── sensor_response.py    # LTR390 R(λ) from datasheet; raw_to_irradiance()
├── forward_model.py      # S = ∫ I_TOA · R · exp(-σ·SCD) dλ — vectorized
├── retrieval.py          # Inverts forward model: signal -> VCD; differentiates profile
├── omi_anchor.py         # earthaccess + sentinelsat; collocation; calibration k
├── climatology.py        # McPeters/Labow tropospheric column priors
├── validation.py         # Compare to ozonesondes (WOUDC), satellite overpasses
├── plot.py               # Profile plots, uncertainty bands, satellite overlay
└── pipeline.py           # End-to-end: telemetry -> profile JSON for /api/ozone
```

Each module: pure functions, typed signatures, numpy/xarray inputs and outputs. `retrieval.py` returns `xarray.Dataset` with dims `(time,)`, vars `vcd_du`, `vcd_du_err`, `o3_density_z`, `sza`, `flag`. `pipeline.py` writes to `web/lib/data/ozone_profile.json` for the Next.js API at `/api/ozone`.

## 9. External dependencies

- **HITRAN / Serdyuchenko cross-sections**: IUP Bremen <https://www.iup.uni-bremen.de/gruppen/molspec/databases/referencespectra/o3spectra2011/index.html>; HITRAN via `hapi` Python lib.
- **Solar spectrum**: TSIS-1 HSRS at LASP LISIRD <https://lasp.colorado.edu/lisird/data/tsis1_hsrs/>; ATLAS-3 fallback at NASA SBUV solar reference page.
- **Satellite**: NASA Earthdata Login (free), `earthaccess` PyPI. Copernicus Data Space free account for S5P-PAL reprocessed v2.5.
- **Reanalysis temperature profile**: ERA5 via `cdsapi` (Copernicus Climate Data Store) — interpolated to balloon track for T_eff.
- **Solar position**: `pvlib >= 0.10`.
- **WOUDC ozonesonde** (validation): <https://woudc.org/data/explore.php> — nearest station for cross-check.

## 10. Open questions and firmware asks

Data we lack that would materially improve retrieval:
- **20-bit raw UV count** (the big one). uint8 uv_index quantization is the #1 error contributor; raw exposes >3000× more dynamic range.
- **A second UV channel** — even a UVA-only photodiode (Vishay VEML6070 or similar around 365 nm) gives a near-σ-zero reference, enabling true ratio retrieval like Brewer A/D pairs. This drops absolute-anchor dependency.
- **Onboard temperature of the photodiode die** (LTR390 is temp-sensitive ~−0.4%/K) — currently we only have ambient.
- **A horizon-attitude estimate** — MEMS accel gives gravity vector at float, but ascent rotation rates corrupt cosine collection. A magnetometer + quaternion would let us deconvolve detector tilt.
- **Cosine diffuser** — even a tiny PTFE cap (Spectralon equivalent) would cut tilt error from ~10% to ~2%.

Asks for board #2/#3, prioritized:
1. Stream raw 20-bit UV counts (not just uv_index).
2. Add a second UVA-only photodiode at ~370 nm for ratio reference.
3. Add PTFE cosine diffuser.
4. Sample temperature next to UV die.
5. Optional: tiny SiPD at 254 nm (Hartley band) for high-precision sub-band column — much more sensitive but needs solar-blind filter (~$15 from Thorlabs FB250-10).

Key open question to flag back: **what is the LTR390's actual cosine response and field of view at 320 nm?** LITE-ON's datasheet shows visible-band cosine only. If you can put a board on an optical bench with a deuterium lamp + monochromator before flight #2, characterize R(λ,θ) once and we lock down ±5% of the budget.

---

## Sources

- [Serdyuchenko et al. 2014 — High spectral resolution ozone cross-sections, Part 2: Temperature dependence (AMT)](https://amt.copernicus.org/articles/7/625/2014/)
- [Gorshelev et al. 2014 — Cross-sections Part 1: Measurements (AMT)](https://amt.copernicus.org/articles/7/609/2014/)
- [Janssen et al. 2018 — Absolute ozone cross-section at 325 nm HeCd (AMT)](https://amt.copernicus.org/articles/11/1707/2018/)
- [Orphal et al. 2016 — UV/Vis ozone cross-section status report](https://www.iup.uni-bremen.de/UVSAT_material/papers/2016/orphal_jmolspec_2016.pdf)
- [Coddington et al. 2021 — TSIS-1 Hybrid Solar Reference Spectrum (GRL)](https://agupubs.onlinelibrary.wiley.com/doi/full/10.1029/2020GL091709)
- [Lerot et al. 2019 — TROPOMI/S5P total ozone column validation (AMT)](https://amt.copernicus.org/articles/12/5263/2019/)
- [LITE-ON LTR-390UV-01 datasheet](https://optoelectronics.liteon.com/upload/download/DS86-2015-0004/LTR-390UV_Final_%20DS_V1%201.pdf)
- [NOAA Dual-Beam UV Ozone Photometer description (UCAR/ACOM)](https://www.acom.ucar.edu/start/O3noaa_description.pdf)
- [Petropavlovskikh et al. 2005 — Umkehr retrieval algorithm (NOAA GML)](https://www.gml.noaa.gov/grad/neubrew/docs/publications/Petropavlovs_2005GL023323.pdf)
- [NASA-JSC balloon UV photometer (Springer 1985)](https://link.springer.com/chapter/10.1007/978-94-009-5313-0_93)
- [Sentinel-5P TROPOMI Total Ozone Column V2 at GES DISC](https://data.nasa.gov/dataset/sentinel-5p-tropomi-total-ozone-column-1-orbit-l2-5-5km-x-3-5km-v2-s5p-l2-o3-tot-hir-at-ge-6aa23)
- [OMI OMTO3 V003 at GES DISC](https://disc.gsfc.nasa.gov/datasets/OMTO3_003/summary)
- [pvlib solar position (NREL SPA, ±0.0003°)](https://pvlib-python.readthedocs.io/en/stable/reference/solarposition.html)
- [NRLSSI2 / LASP LISIRD solar irradiance](https://earth.gsfc.nasa.gov/climate/projects/solar-irradiance/data)
- [SOLAR-ISS reference spectrum (A&A 2018)](https://www.aanda.org/articles/aa/full_html/2018/03/aa31316-17/aa31316-17.html)
- [Adafruit LTR390 spectral response overview](https://learn.adafruit.com/adafruit-ltr390-uv-sensor/overview-2)
- [BIPM ozone cross-section reference](https://www.bipm.org/en/ozone)
