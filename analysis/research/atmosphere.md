# Atmospheric Retrieval Pipeline — Implementation Plan

> Research output from sub-agent investigation. Covers tropopause detection, vertical wind profile, and gravity wave decomposition from balloon ascent telemetry.
>
> Sample rate context: 5-min uplinks → ~1.5 km vertical sample spacing at typical 5 m/s ascent. Honest vertical resolution ~3 km (Nyquist).

## 1. Tropopause Detection

**WMO 1957 lapse-rate algorithm** is the canonical method but notoriously easy to mis-implement; the original WMO text is ambiguous. Definition: lowest level where dT/dz ≥ -2 K/km **and** the mean lapse rate from that level to all higher levels within the next 2 km also ≥ -2 K/km. Reichler et al. (2003) gives a robust, vectorized formulation: work in pressure coordinates with κ = R/cp, compute Γ = -dT/dz, find the lowest p where Γ crosses 2 K/km, then validate the 2-km integrated criterion. Reference implementation: NCAR's `trop_wmo` in NCL — port that logic, not a hand-rolled one. MetPy's `tropopause_pressure` is in active development (Unidata issue #1324, `tropopauseCalc` repo) and worth tracking, but currently incomplete.

**Cold-point tropopause** is just argmin(T) above ~8 km, capped at a max-altitude threshold (~20 km mid-latitude, ~18 km tropical) to avoid stratospheric warming biases. Cheap and robust — implement first as a sanity check.

**Dynamical tropopause (PV = 2 PVU)** requires absolute vorticity and potential temperature on isentropic surfaces, which means horizontal gradients across grid points. **You cannot compute this from a single balloon track.** It only works if you co-sample ERA5 PV at the balloon's lat/lon/time and read off the 2-PVU surface. Plan to overlay this as a comparison product, not derive it independently. Kunz et al. (2011, JGR 10.1029/2010JD014343) note 2 PVU is increasingly inadequate in the subtropics — a PV-gradient maximum or 1.5–4 PVU latitude-dependent threshold is more defensible.

**Sparse sampling.** At 1.5 km/sample you straddle the typical 2-km validation window — interpolation is mandatory. Use monotone cubic (PCHIP) on T(z), not cubic spline (avoids non-physical overshoot near the tropopause kink). Resample to 100-m grid before applying WMO criteria. Quantify uncertainty by bootstrap-resampling input points and re-running the detector.

**Tropical vs mid-latitude.** Tropical tropopause is higher (~17 km), colder (~190 K), sharper; lapse-rate and cold-point diverge in ~50% of profiles and the cold point sits ~1 km above the lapse-rate point (Pan et al., NOAA 21779). Stratolink-3 will start mid-latitude (lapse-rate ≈ cold-point ~12 km, ~210 K) — both definitions should agree. Disagreement is a flag, not a bug.

## 2. Vertical Wind Profile

**The mechanics:** balloon horizontal position is advected by horizontal wind. Compute (u, v) by differentiating (lon, lat) → (x, y) in a local ENU frame relative to launch, then take dx/dt, dy/dt. Pair with dz/dt (ascent rate, ~5 m/s) to bin by altitude. With 5-min sampling you get one (u, v) per 1.5 km bin — that's your native resolution.

**Smoothing.** Savitzky-Golay (order 2 or 3, window ~5–7 samples) on x(t), y(t) **before** differentiation, then re-differentiate analytically using the SG coefficients. This is the standard radiosonde technique (Press et al. 1990, ADS 1990ComPh...4..669P) and avoids the noise amplification of naive finite differences. LOESS is fine but slower and harder to error-propagate. Splines overshoot near pendulum-induced kinks — avoid for this signal.

**Resolution.** Operationally manufacturers low-pass below 300 m on 5 m/s ascent (AMT 16, 4183, 2023) — you're already coarser. With 5-min sampling, **honest vertical resolution is ~3 km** (Nyquist on 1.5 km sample spacing). Anything advertised below that is interpolation, not signal. Document this explicitly in plot legends.

**Validation.** Two parallel paths:
- **ERA5** via `cdsapi` — `reanalysis-era5-pressure-levels`, request u, v, T at all 37 pressure levels at the balloon's nearest 0.25° grid point and hourly time. Interpolate ERA5 to balloon (lat, lon, p, t). Expect RMS u/v differences of 2–4 m/s in the troposphere, 4–8 m/s in the stratosphere — that's the literature baseline (Tellus A 73, 1929752 for ERA5 vs IGRA tropics).
- **IGRA** via `siphon.simplewebservice.igra2.IGRAUpperAir` — find the nearest WMO station within ~500 km and same launch day. This is "ground truth-ish" but irregularly available.

Library stack: `numpy`, `scipy.signal.savgol_filter`, `pyproj` (Geod for lat/lon distances), `metpy.calc` (wind_components, mixing_ratio_from_relative_humidity), `xarray` + `cdsapi` for ERA5, `siphon` for IGRA.

## 3. Gravity Wave Detection

**The hard constraint:** 1.5 km vertical sampling → 3 km Nyquist wavelength. Gravity waves span 1–10+ km vertical wavelengths. **You will only resolve λz ≳ 3 km waves**, and aliasing is a real risk for the energetic short-wavelength tail. Inertia-gravity waves (the lower-frequency, larger-λz population, 3–10 km) are detectable; high-frequency mesoscale waves are not. Be honest about this in the output.

**Background separation.** Subtract a low-order polynomial (degree 2–3) fit of (u, v, T) vs z over a 4–6 km window — this is the Vincent/Allen 1995 approach and is more robust than a high-pass filter at the profile endpoints. Residuals u', v', T' are the wave perturbations.

**Hodograph analysis** (Vincent & Fritts 1987, JAS): plot u' vs v' over an altitude window. Inertia-gravity waves trace an ellipse; major-axis orientation gives horizontal propagation azimuth (with 180° ambiguity resolved by sign of T'·u' phase lag); axial ratio = f/ω̂ gives intrinsic frequency. Implement as: window the profile (3–5 km segments), fit ellipse via PCA on (u', v'), extract orientation and ratio.

**Stokes parameters** (Eckermann 1996, JGR 10.1029/96JD01578) generalize hodograph to multi-wave / wavelet-banded analysis. Compute I, D, P, Q from u', v' cospectra: I = total wave variance, D = directional preference, P/Q = polarization. Degree of polarization d = √(D² + P² + Q²)/I — high d means coherent single wave, low d means superposition. This is the standard balloon-borne characterization (Zink & Vincent 2001; Wang et al. 2005; Colligan et al. 2020).

**Spectra.** Vertical wavenumber spectrum E(m) ∝ m⁻³ in the saturated regime (Nastrom 1997, JGR 10.1029/96JD03784). Compute via Welch or multi-taper on z-resampled u'(z), v'(z). With your data length expect O(20–50) independent samples over the ascent — enough for a single spectrum, not for trend analysis.

**Pressure-altitude vs GPS-altitude residual.** Compute zₚ from hydrostatic integration of T(p), compare to GPS z. The residual contains real signal (temperature errors, hydrostatic departures during wave events) but is dominated by sensor bias and ascent-rate-dependent thermal lag on the TMP117. Treat as diagnostic, not primary.

**Literature anchor papers (all worth pulling):**
- Vincent & Fritts (1987) JAS 44, 748 — hodograph foundation
- Eckermann (1996) JGR 101, 19169 — Stokes/hodograph equivalence
- Allen & Vincent (1995) JGR 100, 1327 — balloon GW climatology, polynomial detrending
- Fritts & Alexander (2003) Rev. Geophys. 41, 1003 — definitive review
- Hertzog et al. (2008) JAS 65, 3056 — Concordiasi superpressure methodology
- Schoeberl et al. (2017) — Loon balloon spectra, PMC PMC6999652
- Green et al. (2024) JGR 10.1029/2023JD039927 — Loon momentum flux

## 4. External Data Dependencies

- **ERA5** (Copernicus CDS) — primary reanalysis. `cdsapi` Python client, requires `~/.cdsapirc` token. Pressure-level product is sufficient; full L137 ("ERA5-complete") only if you need stratospheric structure above 1 hPa. Cache aggressively — requests are queued and slow (~5–30 min).
- **MERRA-2** (NASA GMAO) — backup. Access via `earthaccess` Python client or OPeNDAP. Comparable quality, native 0.5°×0.625°, hourly. Useful as independent cross-check.
- **IGRA v2** (NOAA NCEI) — radiosonde archive via `siphon.IGRAUpperAir`. Find nearest station via `siphon.IGRAStations`. Coverage is best in North America/Europe.
- **NCEP/MERRA-2 tropopause climatologies** — for normal-range bounds. NOAA's tropopause analysis is in `gdas` files; simpler to compute climatology from ERA5 directly on first run and cache.

## 5. Module Layout (`analysis/atmosphere/`)

```
profile.py        — load_telemetry(csv) -> xr.Dataset
                  — to_regular_grid(ds, dz=100m, method='pchip') -> ds
                  — filter_gps_quality(ds, max_hdop=2.0, min_sats=4) -> ds
                  — derive_kinematics(ds) -> ds  # adds u, v, w, dx/dt, dy/dt

tropopause.py     — lapse_rate_wmo(ds) -> dict {z, p, T, method}
                  — cold_point(ds) -> dict
                  — dynamical_from_era5(ds, era5) -> dict  # 2 PVU lookup
                  — detect_all(ds) -> dict {lr, cp, dyn, agreement_flag}

wind.py           — extract_horizontal_wind(ds, window=5, sg_order=2) -> ds with u', v'
                  — bin_by_altitude(ds, dz=500m) -> ds
                  — compare_to_era5(ds, era5_ds) -> ds with bias, rmse

gravity_waves.py  — separate_background(ds, method='poly', degree=2, window_km=5) -> ds
                  — hodograph_fit(u_prime, v_prime, z) -> WaveParams
                  — stokes_parameters(u_prime, v_prime) -> dict {I,D,P,Q,d}
                  — vertical_wavenumber_spectrum(u_prime, dz) -> (m, E_u, E_v)
                  — pressure_gps_residual(ds) -> ds

validation.py     — fetch_era5(lat, lon, t_range, levels) -> xr.Dataset  # cdsapi wrapper
                  — fetch_igra_nearest(lat, lon, date, max_km=500) -> pd.DataFrame
                  — interp_era5_to_track(era5, ds) -> ds
                  — comparison_stats(ds_obs, ds_ref) -> dict

plot.py           — skewt_from_ds(ds) -> Figure  # via MetPy SkewT
                  — hodograph_panel(ds, z_range) -> Figure
                  — wind_profile(ds, era5=None) -> Figure
                  — wavenumber_spectrum(spec) -> Figure
                  — tropopause_overlay(ds, trop_results) -> Figure
```

All modules accept and return `xarray.Dataset` keyed on `time` (raw) or `altitude` (gridded); validation outputs are plain dicts/`pandas.DataFrame` for JSON serialization to the Next.js API.

## 6. Pitfalls

- **33% NOGPS rows.** Filter on `gps_satellites ≥ 4` and `hdop ≤ 2`. Use pressure-derived altitude as fallback (hypsometric integration with T) but flag those rows. Don't interpolate across gaps > 15 min — gravity wave phase is lost.
- **Pendulum motion.** The payload swings under the balloon at ~1–4 Hz; at 5-min sampling this is aliased into broadband noise. Cannot remove without higher-rate IMU data. Use `mems_accel_x/y/z` to detect periods of high oscillation and either flag or attenuate the gravity-wave retrieval window. Schoeberl et al. (2017, PMC6999652) and Podglajen et al. (AMT 7, 1043, 2014) discuss the spectral signature — pendulum sits at much higher frequencies than inertia-GW band, so it doesn't contaminate λz > 3 km retrievals if your sampling is slow enough. Lucky for you, slow sampling actually helps here.
- **Diurnal cycle.** Solar heating biases T by ~1–2 K depending on radiation shield; quantify by comparing day vs night ascents. Tide signal at λz ~ 6–10 km can be confused with gravity waves — flag any wave detection that aligns with semidiurnal period.
- **Float altitude.** Once dz/dt → 0, you switch from a vertical profiler to a quasi-Lagrangian tracer (like Concordiasi/Loon). Different physics: track u(t), v(t) at fixed isopycnic surface; compute intrinsic frequency spectrum, momentum flux via Hertzog/Boccara method (JAS 65, 3056). This is its own analysis module — call it `float_analysis.py` when you get there.

## 7. Open Questions to Flag Back

In rough order of payoff:

1. **Sample rate is the dominant limit.** Going from 5 min → 1 min would push Nyquist from 3 km to 600 m, unlocking the bulk of the gravity-wave variance spectrum and dropping wind uncertainty by ~5×. Worth the battery cost?
2. **Add relative humidity sensor.** Enables moist tropopause, cloud-top detection, water-vapor tape recorder signal in the TTL. Roughly equal value to faster sampling for atmospheric science. A small SHT45 or HDC3022 would do it.
3. **TMP117 0.1 °C is fine** for tropopause but limits gravity-wave T' detection — typical T' amplitudes are 0.5–2 K, so you're SNR-marginal in quiet conditions. 0.01 °C (e.g., a precision thermistor with delta sigma readout) would noticeably help GW detection but is not the bottleneck.
4. **9-DoF IMU at higher rate.** A logged-onboard 50–100 Hz accel/gyro stream (even if not uplinked, just summarized) would let you actually subtract pendulum motion rather than just flagging it.
5. **Two-frequency GPS or barometric Kalman filter on-payload.** Reduces altitude noise floor below the gravity-wave T' signal, important for hydrostatic residual analysis.

---

## Key URLs

- Reichler tropopause: https://www.inscc.utah.edu/~reichler/research/projects/TROPO/2003GL018240.pdf
- NCL trop_wmo: https://www.ncl.ucar.edu/Document/Functions/Built-in/trop_wmo.shtml
- Eckermann Stokes/hodograph: https://agupubs.onlinelibrary.wiley.com/doi/abs/10.1029/96JD01578
- Fritts & Alexander review: https://agupubs.onlinelibrary.wiley.com/doi/10.1029/2001rg000106
- Loon balloon GW spectra (Schoeberl): https://pmc.ncbi.nlm.nih.gov/articles/PMC6999652/
- Loon momentum flux (Green 2024): https://agupubs.onlinelibrary.wiley.com/doi/10.1029/2023JD039927
- Superpressure response to GW (Podglajen): https://amt.copernicus.org/articles/7/1043/2014/
- Strateole-2 equatorial waves: https://acp.copernicus.org/articles/22/15379/2022/
- Concordiasi GW momentum flux: https://agupubs.onlinelibrary.wiley.com/doi/10.1002/2015JD024253
- Nastrom vertical wavenumber spectra: https://agupubs.onlinelibrary.wiley.com/doi/abs/10.1029/96JD03784
- ERA5 vs IGRA tropics: https://www.tandfonline.com/doi/full/10.1080/16000870.2021.1929752
- Siphon IGRA: https://unidata.github.io/siphon/latest/examples/upperair/IGRA2_Request.html
- cdsapi: https://github.com/ecmwf/cdsapi
- Balloon drift estimation: https://gmd.copernicus.org/articles/17/3783/2024/
- High-res radiosonde winds: https://amt.copernicus.org/articles/16/4183/2023/
- WMO tropopause dilemma (2025): https://egusphere.copernicus.org/preprints/2025/egusphere-2024-4198/
- Kunz dynamical tropopause: https://agupubs.onlinelibrary.wiley.com/doi/full/10.1029/2010JD014343
- Stanford Loon writeup: https://sustainability.stanford.edu/news/gravity-wave-insights-internet-beaming-balloons
- Tropical lapse rate vs cold point (NOAA): https://repository.library.noaa.gov/view/noaa/21779
