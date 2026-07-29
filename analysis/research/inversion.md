# Advanced Ozone Inversion Algorithms — Research Report

> Deep-dive follow-up to `ozone.md`. Surveys techniques that could push retrieval accuracy from ±10–15% column to ±5–7%. Top three actionable lifts: joint multi-altitude OEM, `ambient_lux` ratio retrieval, quantization-aware S_ε.

The current Beer-Lambert + differential approach is sound for a first paper but leaves substantial accuracy on the table. The fundamental gain comes from **treating the entire ascent as one joint inverse problem rather than N independent inversions**, and adding a Bayesian regularizer (OEM or Tikhonov) to suppress the noise amplification that the d/dz differentiation introduces. Everything else is icing.

## 1. Optimal Estimation Method (Rodgers 2000)

- **Paper**: Rodgers, *Inverse Methods for Atmospheric Sounding: Theory and Practice* (World Scientific, 2000); see also [Maahn et al. 2020 BAMS](https://repository.library.noaa.gov/view/noaa/31068/noaa_31068_DS1.pdf) as the modern teaching reference.
- **Math sketch**: Minimize J(x) = (y − F(x))ᵀ S_ε⁻¹ (y − F(x)) + (x − x_a)ᵀ S_a⁻¹ (x − x_a). For our case y is the vector of N ascent measurements (one broadband signal per altitude bin, dimension N ≈ 20–40 for a 5-min cadence ascent), x is the ozone number-density profile on a 1-km vertical grid, F is the layered Beer-Lambert forward model with σ_eff(T,SCD) baked in. Iterate Levenberg-Marquardt: x_{i+1} = x_a + (KᵀS_ε⁻¹K + S_a⁻¹ + γD)⁻¹ KᵀS_ε⁻¹[y − F(x_i) + K(x_i − x_a)]. The averaging-kernel A = (KᵀS_ε⁻¹K + S_a⁻¹)⁻¹KᵀS_ε⁻¹K and DOFS = tr(A) quantify how many independent profile pieces we actually recover (Sutton et al., [AMT 12, 2097, 2019](https://amt.copernicus.org/articles/12/2097/2019/) report DOFS ≈ 4–8 for stratospheric lidar; our single-broadband case will likely give DOFS ≈ 2–3).
- **S_a**: McPeters & Labow climatology ([JGR 2012, 10.1029/2011JD017006](https://agupubs.onlinelibrary.wiley.com/doi/abs/10.1029/2011jd017006)) supplies layer means; for the covariance use 50% 2σ variance on the diagonal and a tent-function correlation length of ~6 km (the [Sutton 2019 OEM lidar paper](https://amt.copernicus.org/articles/12/2097/2019/) and [Bak et al. AMT 2019](https://amt.copernicus.org/articles/12/4745/2019/) describe construction in detail).
- **S_ε**: For us this is dominated by uv_index quantization. Compute the variance of a uniform distribution on [u−0.5, u+0.5] = 1/12 (in uv_index units), then propagate through `raw = uv_index·2300`, plus shot noise ~√raw, plus a 2% systematic.
- **Python**: [pyOptimalEstimation by Maahn](https://github.com/maahn/pyOptimalEstimation) (GPL-3, actively maintained, Rodgers reference); [NASA PSG retrievalOE](https://github.com/nasapsg/retrievalOE) (planetary, but the OE code is generic); ARTS 2.6's [PyARTS](https://www.radiativetransfer.org/tools/) (heavy but the gold standard, [Eriksson 2025 JQSRT](https://www.sciencedirect.com/science/article/pii/S0022407325001050)). pyOptimalEstimation is the right starting point — it takes any Python `forward_model(x)` callable, computes K via finite differences, and runs L-M.
- **Accuracy lift**: 30–50% RMS reduction over differential inversion in the stratospheric core, dramatic at profile edges (lidar OEM example: <10% from sondes 15–25 km vs. ~25% un-regularized).
- **Effort**: Medium (1–2 weeks to wire pyOptimalEstimation around our existing forward model).
- **Verdict**: **Adopt.** This is the right backbone.

## 2. Tikhonov / Phillips-Tikhonov regularization

- **Paper**: [Hasekamp & Landgraf, JGR 2001, 10.1029/2001JD000636](https://agupubs.onlinelibrary.wiley.com/doi/abs/10.1029/2001JD000636) (first non-climatology UV ozone profile retrieval); [Steck 2002](https://www.atmosp.physics.utoronto.ca/~dbj/PHY2506/steck2002_constraint.pdf) on parameter selection; [Xu et al. AMT 2014](https://amt.copernicus.org/articles/7/523/2014/amt-7-523-2014.pdf) "Insights into Tikhonov regularization"; [Atmosphere 11, 1052 (2020)](https://www.mdpi.com/2073-4433/11/10/1052).
- **Math sketch**: min ‖y − Kx‖² + λ‖Lx‖². L = I (norm), L = first-difference (smoothness), or L = second-difference (curvature). λ from L-curve corner (Hansen 2010) or GCV. Equivalent to OEM with S_a = (λLᵀL)⁻¹ and x_a = 0, but no climatology required.
- **Why for us**: When the McPeters/Labow prior is suspect (polar-vortex flights, ozone-hole edge), Tikhonov gives a climatology-free fallback. Also simpler to debug.
- **Python**: [pinvprob3 by Kawahara](https://github.com/HajimeKawahara/pinvprob) (GPL-2) implements TSVD + Tikhonov + L-curve directly. Or roll-your-own with `scipy.linalg.lstsq` + `numpy.gradient` for L.
- **Accuracy lift**: Comparable to OEM in DOFS, ±10% RMS in stratosphere per Hasekamp & Landgraf.
- **Effort**: Low (a few hundred lines).
- **Verdict**: **Adopt as fallback.** Run both, compare, ship OEM as primary and Tikhonov as climatology-independent sanity check.

## 3. Differentiable forward model (JAX) and ML surrogates

- **Paper**: [Kawahara et al. ApJ 985, 263 (2025) — ExoJAX2](https://iopscience.iop.org/article/10.3847/1538-4357/adcba2); [Brence et al. Springer ML 2022 — RT surrogates for trace gas](https://link.springer.com/article/10.1007/s10994-022-06155-2); FP_ILM (Loyola et al.) is the only published NN-emulated ozone retrieval.
- **Math sketch**: Implement the band-integrated Beer-Lambert forward S(x) = ∫ I_TOA(λ) R(λ) exp(−σ(λ,T) · A·x) dλ in JAX. JAX `jax.jacrev(F)` gives K analytically and exactly — no finite differences, no σ_eff lookup-table interpolation errors. Couples cleanly with NumPyro for #4.
- **Why for us**: Our forward model is trivially JAX-able — it's a linear-in-exponent expression. Jacobians are needed for OEM iteration; analytic K is faster and more accurate than the finite-difference K pyOptimalEstimation computes.
- **Python**: [ExoJAX](https://github.com/HajimeKawahara/exojax) (overkill but instructive); just write our own 50-line JAX forward model.
- **Effort**: Low–medium.
- **Verdict**: **Adopt** at integration time — costs little, unlocks #4 and gives exact gradients into L-M.

A full neural-network surrogate of libRadtran is overkill: we don't need full radiative transfer (no multiple scattering at our altitudes for direct-sun geometry). Skip.

## 4. Bayesian MCMC / HMC retrieval

- **Paper**: [NumPyro](https://num.pyro.ai/) (Pyro-PPL, JAX-backed NUTS). No published HMC ozone profile retrieval that I could find — there's an obvious paper here if we wanted it.
- **Math sketch**: Same likelihood as OEM, but instead of point-estimate optimization, sample p(x|y) ∝ exp(−J(x)/2). Returns full posterior over the profile.
- **Why for us**: Quantization-dominated noise is decidedly non-Gaussian — the L-M Gaussian assumption mis-states uncertainty. HMC gives rigorous credible intervals.
- **Cost**: ~1000× the OEM run, ~1 minute per flight (~20-dim state).
- **Effort**: Medium (NumPyro model definition + diagnostics).
- **Verdict**: **Consider** for the methods paper as a post-hoc uncertainty cross-check; not for the live pipeline.

## 5. Joint multi-altitude inversion — **THE BIG ONE**

- **Paper**: [van der A et al., JGR 2002, 10.1029/2001JD000696](https://agupubs.onlinelibrary.wiley.com/doi/full/10.1029/2001JD000696) (GOME profile retrieval); [Liu et al. JGR 2005, 10.1029/2005JD006240](https://agupubs.onlinelibrary.wiley.com/doi/abs/10.1029/2005JD006240) (GOME OEM with full validation); SCIAMACHY limb inversion comparisons in [J. Earth Sci. 2022](https://link.springer.com/article/10.1007/s12583-022-1766-2).
- **Math sketch**: Instead of inverting each altitude independently for VCD(z) then differentiating, stack: y = [S(z_1), S(z_2),...,S(z_N)]ᵀ, x = [n(layer_1),...,n(layer_M)]ᵀ, K_{ij} = ∂S(z_i)/∂n(layer_j) = −σ_eff · path_length_ij · S(z_i). The system is **over-determined** (N > M with N ≈ 30 ascent samples vs M ≈ 10–15 profile layers), and regularized inversion is far more stable than differentiating noisy column estimates.
- **Why for us**: This eliminates the differentiation-noise-amplification problem that dominates the current approach. The differential method effectively throws away the correlations between adjacent altitude samples that the joint inversion exploits.
- **Effort**: Low — same code as #1, just a different K structure.
- **Verdict**: **Adopt immediately.** This is the single biggest accuracy lever.

## 6. Dequantization for the uint8 problem

- **Paper**: Maximum-entropy-on-mean ([Bocquet QJRMS 2005, 10.1256/qj.04.67](https://rmets.onlinelibrary.wiley.com/doi/10.1256/qj.04.67)) is the closest atmospheric analog; classical reference is Gray & Neuhoff IEEE IT 1998.
- **Sketch**: A uint8 reading u means raw ∈ [(u−0.5)·2300, (u+0.5)·2300]. Treat as a uniform likelihood, not a delta function — incorporate directly in S_ε within the OEM framework (off-diagonal). Adjacent monotone-altitude samples constrain the underlying continuous trajectory: if u(z) jumps between two bins, it must have crossed the boundary at a specific z.
- **Effort**: Low (re-derive S_ε with proper uniform-quantization variance).
- **Verdict**: **Adopt.** Almost free, recovers ~30% of the quantization-budget hit.

Compressed sensing isn't a fit here — our profile is dense, not sparse. Skip.

## 7. Auxiliary data — ratio retrieval

- **Reference**: Brewer/Dobson A/D pair principle ([WMO 2021 docs](https://amt.copernicus.org/articles/14/4915/2021/)); AERONET inversion ([Dubovik & King JGR 2000](https://agupubs.onlinelibrary.wiley.com/doi/10.1029/2000JD900282)).
- **Sketch**: `ambient_lux` (~550 nm peak, σ_O3 ≈ 0 except a tiny Chappuis contribution) is effectively a reference channel. Ratio S_UV/S_lux removes I_TOA solar-cycle drift, attitude/cosine error (common-mode), and most aerosol scattering (Ångström extrapolation). It does *not* remove ozone absorption — that's the signal we want. This converts our retrieval into a Dobson-style ratio measurement, dropping absolute-anchor dependency and the dominant cosine error term.
- **Effort**: Low. Add a second forward-model channel for ambient_lux, joint-invert.
- **Verdict**: **Adopt.** Plus ERA5 T(z) for σ(T), and `solar_voltage` correlation as a glint flag — both cheap additions.

---

## Top 3 recommendations

1. **Joint OEM inversion using pyOptimalEstimation** with a JAX forward model. Stack all ascent samples, solve once for the profile on a 1-km grid using McPeters/Labow prior + tent covariance + Sutton-style S_ε.
2. **Ratio retrieval with `ambient_lux` as reference channel.** Cuts dominant systematic errors with no hardware change.
3. **Proper quantization-aware S_ε.** Treat uint8 as uniform-likelihood. Stack a Tikhonov-regularized variant as climatology-free cross-check.

## Proposed retrieval algorithm (one-page schematic)

```
INPUT: 5-min ascent telemetry {z_i, T_i, p_i, uv_i, lux_i, SZA_i, lat_i, lon_i}, i=1..N

1. Filter rows: SZA < 80°, no glint flag, z > 8 km
2. Build joint measurement vector y = [uv_1*2300, ..., lux_1, ...] of length 2N
3. State vector x = [n_O3(layer_1), ..., n_O3(layer_M)] on 1-km grid, M ≈ z_max−8
4. A priori x_a, S_a from McPeters/Labow 2012 at flight (lat, month); diag = (0.5 x_a)^2,
   off-diag = exp(-|Δz|/6km)
5. Forward model F_JAX(x, T, SZA):
   S_uv(z) = ∫280-430 I_TOA(λ) R_uv(λ) exp(-σ(λ,T(z)) AMF(SZA,z) ∫_z^TOA n dz') dλ
   S_lux(z) = ∫400-700 I_TOA(λ) R_lux(λ) exp(-σ_Chappuis AMF(SZA,z) col(z)) dλ
   K = jax.jacrev(F_JAX)(x)
6. S_eps: diag = quant_var(2300^2/12) + shot_var(raw_i) + 0.02^2 * y_i^2
7. Iterate Levenberg-Marquardt (Rodgers Eq. 5.36) until ||Δx||_Sa < 1e-2:
   x_{k+1} = x_a + (K^T S_eps^-1 K + S_a^-1 + γI)^-1 K^T S_eps^-1 [y - F(x_k) + K(x_k - x_a)]
8. Compute A, DOFS, error covariance S_x = (K^T S_eps^-1 K + S_a^-1)^-1
9. Cross-check with Tikhonov (L=second-derivative, λ from L-curve)
10. Anchor: rescale to match TROPOMI column (extrapolation 0→z_min via x_a tropospheric layer)
11. Emit xarray Dataset with profile, S_x, A, DOFS, anchor-scale k
```

## Realistic accuracy estimate

Current plan: ±10–15% column, ±20–30% profile RMS.

With OEM + joint + ratio + quant-aware S_ε:

| Term | Now | After |
|---|---|---|
| Quantization | ±5–8% | ±2–3% (quant-aware likelihood) |
| Cosine response | ±5–10% | ±2% (ratio common-mode rejection) |
| Profile shape RMS | ±20–30% | **±8–12%** (joint inversion + regularization) |
| Column | ±10–15% | **±5–7%** |

This becomes competitive with mid-quality ozonesondes (≈5% precision) for column and within 2× for profile shape — a genuine science product, not just a methods note. The methods paper at AMT becomes considerably stronger.

## Sources

- [Maahn et al. 2020 — Optimal Estimation Retrievals (BAMS)](https://repository.library.noaa.gov/view/noaa/31068/noaa_31068_DS1.pdf)
- [Sutton et al. 2019 — DIAL OEM Stratospheric Ozone (AMT)](https://amt.copernicus.org/articles/12/2097/2019/)
- [McPeters & Labow 2012 — Ozone Climatology (JGR)](https://agupubs.onlinelibrary.wiley.com/doi/abs/10.1029/2011jd017006)
- [Bak et al. 2019 — Ozone profile climatology (AMT)](https://amt.copernicus.org/articles/12/4745/2019/)
- [Hasekamp & Landgraf 2001 — UV Phillips-Tikhonov (JGR)](https://agupubs.onlinelibrary.wiley.com/doi/abs/10.1029/2001JD000636)
- [van der A et al. 2002 — GOME profile recalibrated (JGR)](https://agupubs.onlinelibrary.wiley.com/doi/full/10.1029/2001JD000696)
- [Liu et al. 2005 — GOME OEM profile + validation (JGR)](https://agupubs.onlinelibrary.wiley.com/doi/abs/10.1029/2005JD006240)
- [Xu et al. 2014 — Insights into Tikhonov for trace-gas (AMT)](https://amt.copernicus.org/articles/7/523/2014/amt-7-523-2014.pdf)
- [Atmosphere 11, 1052, 2020 — Tikhonov construction](https://www.mdpi.com/2073-4433/11/10/1052)
- [Eriksson et al. 2025 — ARTS 2.6 deep Python (JQSRT)](https://www.sciencedirect.com/science/article/pii/S0022407325001050)
- [Kawahara et al. 2025 — ExoJAX2 differentiable RT (ApJ)](https://iopscience.iop.org/article/10.3847/1538-4357/adcba2)
- [Brence et al. 2022 — RT surrogates for trace gas (ML)](https://link.springer.com/article/10.1007/s10994-022-06155-2)
- [Bocquet 2005 — Max-entropy atmospheric inversion (QJRMS)](https://rmets.onlinelibrary.wiley.com/doi/10.1256/qj.04.67)
- [Dubovik & King 2000 — AERONET retrieval (JGR)](https://agupubs.onlinelibrary.wiley.com/doi/10.1029/2000JD900282)
- [pyOptimalEstimation (GitHub, GPL-3)](https://github.com/maahn/pyOptimalEstimation)
- [pinvprob3 (GitHub, GPL-2)](https://github.com/HajimeKawahara/pinvprob)
- [NASA PSG retrievalOE (GitHub)](https://github.com/nasapsg/retrievalOE)
- [ARTS Tools (radiativetransfer.org)](https://www.radiativetransfer.org/tools/)
- [NumPyro docs](https://num.pyro.ai/en/latest/mcmc.html)
