# UV Ozone Retrieval — Open-Source Code Survey

> Deep-dive follow-up to `ozone.md` and `inversion.md`. Surveys actual libraries and reference code we can use or learn from. Headline finding: libRadtran + pyLRT + pyOptimalEstimation + HARP + ussa1976 is the right open-source stack, lifting realistic accuracy to ±8-10% column / ±15-20% profile. Below that, quantization floor binds — only a firmware change unlocks further.

## Radiative Transfer Forward Models

Candidates for our forward model. We need ground-to-balloon UV transmission with ozone Beer-Lambert as the dominant term, scattered light secondary at SZA < 75.

- **libRadtran 2.0.6** (GPL-3, Dec 2024 release) — gold standard. uvspec handles 250-1200 nm, supports `mol_modify O3 <DU> DU`, Chapman pseudo-spherical geometry, DISORT/MYSTIC solvers. Fortran/C core; install is non-trivial (configure/make + optical-property modules). <https://www.libradtran.org/doku.php?id=download>
  - **pyLRT** (BSD-3, v0.2.2 Jun 2024) — thinnest reasonable Python wrapper; manages uvspec options, parses output to `xarray.DataArray`. 34 commits, modest maturity, but exactly the right abstraction. <https://github.com/EdGrrr/pyLRT>
  - **libradtranpy** (MIT, 50 commits, active) — LSST/DESC's wrapper, more opinionated; exposes `ozone` (DU) as an explicit kwarg in 200–400 DU range, has a directory-based simulation manager. Built for astronomy calibration but the API is right. <https://github.com/LSSTDESC/libradtranpy>
  - **Verdict**: install libRadtran + pyLRT. Use it to (a) build the `σ_eff(T, SCD)` LUT once with proper multiple-scattering correction, (b) generate ground-to-balloon transmission curves for forward-model validation, (c) optionally serve as the inner loop for an OE retrieval. Adds zero runtime cost in production if we cache LUTs.

- **PythonicDISORT** (MIT, v1.6 Feb 2026, active) — pure-Python reimplementation of Stamnes DISORT, multi-layer, delta-M scaling, NT corrections, BDRF. Slower than Fortran but installable with `pip install pythonic-disort`, no compilers. Good for "what does the cloud below me look like in 320 nm scattered light" sensitivity studies. <https://github.com/LDEO-CREW/Pythonic-DISORT>
- **pydisort** (Apache-2 via JOSS) — modern C++/PyTorch DISORT, parallelized, `pip install pydisort` no compile. Useful if we want batch-process every telemetry sample. <https://joss.theoj.org/papers/685a176197f637c63d4f7c091620a847>
- **SCIATRAN / pyatran** (pyatran 0.3.1, last released 2018; SCIATRAN itself requires academic registration). Heavyweight, limb-geometry-centric, the right tool for multi-tangent-height limb retrievals — overkill for our nadir-direct-beam case. <https://pyatran.readthedocs.io>
- **TUV** (NCAR ACOM, public Fortran) and the `TUV-batch-python` wrapper. UV/visible flux model; not as flexible as libRadtran but simpler. <https://github.com/fzhao70/TUV-batch-python>
- **NEMESISPY / archNEMESIS** (GPL-3, v1.0.6 Dec 2025) — Python optimal-estimation retrieval framework with correlated-k, nested sampling, both nadir/limb/occultation. Designed for planetary atmospheres but architecturally well-suited; could be adapted to Earth UV ozone if we provide cross-sections and TOA solar in correlated-k tables. <https://github.com/juanaldayparejo/archnemesis-dist>
- **Py4CAtS** (DLR, restricted distribution, v4.0 Oct 2024) — line-by-line atmospheric spectroscopy, mostly thermal-IR focused. Not the right tool for broadband UV. <https://atmos.eoc.dlr.de/tools/Py4CAtS/>

## Retrieval / Inversion Frameworks

- **pyOptimalEstimation** (GPL-3, v1.3 Oct 2023) — Rodgers 2000 OE with arbitrary user-supplied forward model. ~130 commits, examples cover MWR/cloud-radar (not ozone) but the framework is generic. **This is the right framework to lift us from analytical Beer-Lambert to formal OE with averaging-kernel diagnostics**. Pass our libRadtran-or-LUT forward model as `f(x) -> y`, provide Jacobian by finite difference, supply a priori `(x_a, S_a)` from McPeters-Labow climatology. <https://github.com/maahn/pyOptimalEstimation>
- **ReFRACtor framework** (NASA JPL, ~2300 commits, C++ + SWIG Python). "Reusable Framework for Retrieval of Atmospheric Composition" — production-grade OE retrieval, has OMPS / CrIS interfaces, handles UV to thermal. Heavy install but if we wanted Earth-style operational retrievals this is the framework. <https://github.com/ReFRACtor/framework>
- **QDOAS** (BIRA-IASB, BSD-3, v3.7.10 Jan 2026, 419 commits, actively maintained on conda-forge) — flagship DOAS retrieval for trace gases from UV-Vis spectrometers. **C++ only, no Python API** (just CLI `doas_cl`). Not directly callable from our pipeline, but the DOAS math (slant column → AMF → VCD) is exactly the formal version of what we're doing analytically. Useful as reference implementation; we cannot reuse the code. <https://github.com/UVVIS-BIRA-IASB/qdoas>
- **woudc-umkehr** (NOAA, MIT, Python wrapper around Petropavlovskikh 2005 Fortran). Production Umkehr retrieval — uses scattered zenith UV at varying SZA to retrieve profile shape, not directly applicable to balloon ascent geometry, but the algorithm structure (Chahine + a-priori-constrained iterative) is informative. <https://github.com/woudc/woudc-umkehr>
- **Tikhonov-regularization examples**: `monego/tikh` and `njchiang/tikhonov` are toy. Better path: implement Tikhonov inside `pyOptimalEstimation` by setting `S_a^{-1} = α · L^T L`. The 2020 MDPI paper *Insight into Construction of Tikhonov-Type Regularization for Atmospheric Retrievals* (<https://www.mdpi.com/2073-4433/11/10/1052>) is the right cookbook.

## Data Access and Reference Data

- **earthaccess** (NASA) + **pys5p** + `sentinelsat` / `cdsetool` — all fine for downloading TROPOMI/OMI L2. Use what we already planned. <https://pypi.org/project/pys5p/>
- **s5p-tools** (<https://github.com/bilelomrani1/s5p-tools>) and **pytropomi** (<https://github.com/bugsuse/pytropomi>) — convenience wrappers; thin enough we don't need them but easy to crib from for the `omi_anchor.py` module.
- **HARP / Atmospheric Toolbox** (stcorp, BSD-3, v1.30 Jan 2026) — *not* a retrieval toolkit. Pure data-harmonization (regridding, unit conversion, collocation). **Use it as the workhorse for satellite collocation**: HARP can ingest S5P, OMI, sondes, ground stations, and harmonize to a common grid in one command. <https://github.com/stcorp/harp>
- **HAPI / HAPI2** (HITRAN, public domain-ish) — line-by-line, primarily IR. For UV ozone cross-sections we still pull Serdyuchenko 2014 ASCII files directly from IUP Bremen; HAPI is not the right tool. <https://github.com/hitranonline/hapi>
- **woudc-extcsv** (MIT, v0.6 Mar 2025) — read/write WOUDC ECSV ozonesonde files. Drop-in for validation. <https://github.com/woudc/woudc-extcsv>
- **pyatmos / ussa1976 / fluids.atmosphere** — three near-equivalent US-Std-Atm-76 implementations. **Pick `ussa1976`** (cleanest API). <https://pypi.org/project/ussa1976/>
- **PyMicrotops / PyMicrotops3** (NERC-FSF) — direct-sun handheld photometer processing including ozone bands; closest existing Python code to the spirit of what we're doing. Worth reading. <https://github.com/NERC-FSF/PyMicrotops3>
- **PhotometerV4_python** (Garrido et al. 2021) — LED-based sun-photometer Python with explicit `ozone_model.py`. Tiny, but exactly the kind of algorithm shape we want for a single-channel broadband detector. <https://github.com/spel-uchile/PhotometerV4_python>

## Picoballoon / Amateur Science

Confirms the earlier finding: **there is no extant open-source amateur HAB ozone retrieval pipeline**. HASP UNF/UND payloads use nanocrystalline gas sensors with UV photodiodes but no published Python code. StratoCore (<https://github.com/dastcvi/StratoCore>, LASP Strateole-2) is instrument control firmware, not retrieval. B-BOP (LMD, Hartley-band 250 nm balloon photometer) is the right scientific reference but its processing code is not public.

## Top 5 Libraries to Integrate

1. **libRadtran + pyLRT** — generate `σ_eff(T, SCD)` LUT with multiple-scattering correction; lifts σ_eff ambiguity from ±3-5% to ±1-2%. <https://github.com/EdGrrr/pyLRT>
2. **pyOptimalEstimation** — replace analytical Beer-Lambert inversion with formal Rodgers OE; gives averaging kernels, posterior covariance, a-priori-aware profile retrieval from differential ascent. Estimated lift: column ±15% to ±10-12%, profile ±25% to ±18%. <https://github.com/maahn/pyOptimalEstimation>
3. **HARP** — collocation with TROPOMI/OMI/sondes, regridding, unit conversion. Replaces ~200 lines of hand-rolled collocation code. <https://github.com/stcorp/harp>
4. **ussa1976** — pressure→altitude conversion. Trivial but correct. <https://pypi.org/project/ussa1976/>
5. **woudc-extcsv** — read WOUDC ECSV ozonesonde files for validation. <https://github.com/woudc/woudc-extcsv>

## Top 3 Algorithm Papers to Adopt

1. **Egli et al. 2022, AMT 15, 1917** — *Traceable total ozone column retrievals from direct solar spectral irradiance measurements in the UV*. The QASUME LSF algorithm formalizes everything we're doing analytically and is the closest published methodological match to a "direct-sun in-situ UV" retrieval (code is request-only, but the math is sufficient). <https://amt.copernicus.org/articles/15/1917/2022/>
2. **Petropavlovskikh et al. 2005, GRL 32, L16808** — Umkehr UMK04. Even though the geometry is different, the iterative profile inversion under a-priori constraint is the algorithm we'd build inside pyOptimalEstimation. <https://doi.org/10.1029/2005GL023323>
3. **McPeters & Labow 2012, JGR 117, D10303** + the 2021 AMT update by Wargan et al. (<https://amt.copernicus.org/articles/14/6407/2021/>) — gives us the climatological prior `x_a` and `S_a` for stratospheric profile shape, essential for OE.

## Gaps Where We Still Write Our Own Code

- **LTR390 spectral response model `R(λ, θ)`** — no library has this; must digitize datasheet and ideally bench-characterize before flight 2.
- **Differential SCD → local number density via ascent finite-difference** with proper error propagation. None of the OE frameworks handles "single broadband detector ascending through the column" out of the box; we wrap pyOptimalEstimation with this state vector mapping ourselves.
- **TROPOMI ↔ balloon collocation calibration `k` per overpass** — straightforward, but no existing helper.
- **Cosine response / glint detection** — entirely bespoke.

## Realistic Best-Case Accuracy

With the best available open-source stack (libRadtran forward model + pyOptimalEstimation + HARP collocation + Serdyuchenko cross-sections + McPeters-Labow prior), and given the **uint8 `uv_index` quantization is fundamentally a ±5-8% floor**, realistic best-case becomes:

- **Total column above float (>15 km)**: **±8-10%** (down from ±15%). Quantization dominates; lift comes from σ_eff LUT accuracy and proper OE absolute anchor.
- **Ascent profile (1–2 km vertical bins)**: **±15-20%** (down from ±25-30%). Lift comes from OE averaging-kernel-aware smoothing rather than naive finite differences.

To break ±8% on column you must fix the firmware: 20-bit raw counts and a second UVA reference channel. Software alone cannot beat the quantization floor.
