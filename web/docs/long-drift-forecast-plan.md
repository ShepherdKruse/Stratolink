# Plan: good forecasts for long-drifting (GPS-dark) balloons

> **Status (branch `forecast-long-drift`):**
> - **P0 — done.** lon-wrap + truncate-on-exit (`gfsGrid.ts`, `balloonIntegrate.ts`),
>   coverage cap + `coverage_limited`/`modeled_hours` honesty (`monteCarloForecast.ts`),
>   UI "position uncertain since {date}" pill (`useForecastPath.ts`, `MissionControl.tsx`).
> - **P1 — done.** Trajectory tube for the forecast cube **and** every GEFS/AIGEFS
>   member cube (`gfs_ingest.py` shared helpers; `gefs_ingest.py`/`aigefs_ingest.py`
>   member tubes; `.slwc` v2 per-slice origins in `windCube.ts`). Verified locally
>   (stratolink-3, 452 h gap): paths follow real winds, members self-center, honest
>   truncation, no globe-wrap.
> - **P2 — largely obviated.** "Size the tube to the cloud" is unnecessary for member
>   tubes: each member is integrated through its *own* tube with the same neutral
>   bias / zero perturbation, so it rides the box center and never hits the wall.
>   The predictability-horizon half is handled by `DEAD_RECKON_CAP_H`. (Only the
>   *parametric-fallback* ensemble — no GEFS members — can diverge from the fc tube;
>   P0 truncation keeps that honest.)
> - **P3 — remaining.** (a) Altitude/level drift (multi-level cube + vertical
>   sampling) — the backtest's biggest error lever; a separate, larger effort
>   touching the cube schema + `sampleWind` + all three ingests. (b) Seed the
>   dead-reckon "now"-uncertainty into the forward Monte Carlo (moot for very-stale,
>   where "now" isn't reached). Formal scored backtest lives on branch
>   `backtest-harness` (own correct integration — already validated the *technique*;
>   the tube brings production in line with it).


> Goal: make the predicted path + uncertainty for a balloon that has been GPS-dark
> for days-to-weeks as accurate and honest as the physics allows — instead of the
> current behavior, where the path is advected by clamped edge winds and lands in a
> fictitious place.

## 1. What's broken today (evidence)

For `stratolink-3` (last real fix **May 29**, ~18 days dark, gap 429 h) the live
forecast draws a confident line that wraps the globe to Hudson Bay and "blasts
through" a ridge. Investigation showed it is **not following the winds** for most
of its length. Three independent root causes:

1. **No longitude wrapping.** `integrateBalloonPathT` accumulates `lon += …` with no
   wrap (`lib/wind/balloonIntegrate.ts:141`), and `windAt` clamps
   `Math.max(lon0, Math.min(lonMax, lon))` with no wrap (`lib/wind/gfsGrid.ts`). Once
   the unwrapped longitude passes the box's east edge (+37°), every sample returns
   that edge meridian's wind, and the longitude **never returns into the box** — so
   ~86% of the path is one constant edge-wind extrapolation, and the displayed
   "Hudson Bay" position is a normalized-longitude mirage.
2. **Cube coverage is capped below what the compute integrates.** Ingest builds the
   forecast cube spanning only `HORIZON_H + min(gap, MAX_GAP_H)` = `24 + 72` ≈ **96 h**
   of time and a box padded `PAD_CAP_DEG = 32°` (`scripts/gfs_ingest.py:40,58,396`).
   But the compute integrates the **full** gap: `spanHours = gapH + TOTAL_HOURS`
   (`lib/wind/monteCarloForecast.ts:356`) ≈ 453 h. Beyond 96 h the time index clamps
   to the **last grid** (`sampleWind` clamp, `windCube.ts:228`); beyond 32° the space
   clamps to the **edge** — double-degenerate.
3. **Edge extrapolation instead of honesty.** `windAt` deliberately clamps rather than
   returning zero ("returning zero made trajectories freeze") — reasonable for a
   small overshoot, catastrophic for a trajectory that lives outside the box for days.

Net: for a long drift we integrate a frozen-in-time, edge-clamped wind for the
majority of the path. The single confident line is meaningless.

## 2. Design goals

- The trajectory must **always be inside real wind data** (no edge/time clamping
  driving motion).
- **Correct longitude handling** everywhere (globe-wrapping and dateline-crossing).
- Uncertainty represented **honestly**: at long lead the product is an ensemble
  **cloud**, not a crisp line; cap the horizon where predictability is gone.
- Reuse the existing GEFS/AIGEFS member ensemble (flow-dependent spread is exactly
  what long drifts need) and the runner-compute + `.slwc` cube pipeline.
- Validate against real long flights with the backtest harness.

## 3. Key enabler

The cube format **already stores geometry per time-slice** — each grid carries its own
`lat0/lon0/nLat/nLon` (`windCube.ts` `GfsGrid`), and `windAt` bilinear-interpolates
each grid independently. So a **trajectory-following "tube"** (each time-slice a
moderate box centered on where the balloon is at that time) needs **no cube-format or
sampler rewrite** — only ingest changes + correct sampling. Consecutive slices must
spatially **overlap** so time-interpolation at a fixed point still has both brackets.

## 4. Phased plan

### P0 — Stop the garbage (small, ship first; no recompute-architecture change)
Make the current behavior correct-or-honest, independent of the tube work.
- **Wrap longitude before sampling.** In `windAt` (or `sampleWind`), normalize `lon`
  into the grid's range (and handle a box that crosses ±180 by comparing on a
  wrapped axis). Also keep the integrator's `lon` reasonable. Fixes the globe-wrap
  *and* the latent dateline bug for Pacific balloons.
- **Don't advect on clamped data.** Detect when a sample is outside the cube
  (time or space) and **stop integrating that trajectory there** (truncate) rather
  than extrapolating on edge/last-grid winds. Mark the truncated point.
- **Align compute span to coverage + cap horizon.** Cap `spanHours` to what the cube
  actually covers, and cap the *intended* forecast horizon for very-stale balloons at
  a predictability-based limit (configurable, e.g. ≤ ~5–7 days of dead-reckon).
- **Honesty in the UI for very-stale devices.** When the gap is large, present the
  ensemble cloud / "position uncertain since {date}" instead of a single confident
  line. (Pairs with the map-label / cone work.)

*Outcome:* the live forecast stops showing a fictitious globe-wrapping line; it shows
a bounded, in-data path + cone. This is the priority fix.

### P1 — Trajectory-following "tube" cube (the real architecture fix)
Lay the wind data along the path instead of one static box.
- **Nominal pre-integration in ingest** (`gfs_ingest.py`): cheaply integrate one
  nominal trajectory (control wind, neutral bias) forward over the intended horizon
  to get an approximate position per time-slice.
- **Per-slice windows:** for each time-slice, fetch a moderate box centered on the
  nominal position, sized = base pad + (downwind reach for one step) + a margin for
  ensemble spread, with **overlap** between consecutive slices. Choose grid step per
  slice under the point budget (finer than today's continent box).
- **Build a tube cube** using the existing per-grid geometry; `compute` integrates
  through it unchanged. Extend the cube's **time span** to the full intended horizon
  (remove the 72 h coverage cap for the tube path).
- Apply the same tube to **GEFS/AIGEFS member cubes** (`gefs_ingest.py`,
  `aigefs_ingest.py`) — the ensemble is what matters for long drifts.

### P2 — Size the tube to the ensemble cloud + horizon honesty
- Size each slice's window to the **ensemble cloud** at that time (not just the
  nominal point), so edge members still sample real winds — otherwise members that
  diverge from nominal hit the tube wall. Requires either (a) iterating P1's nominal
  layout with a spread estimate, or (b) the full **march** (interleave fetch ↔
  ensemble-integrate per step; more accurate, but couples Python fetch + TS integrate
  and serializes — defer unless P1+cloud-margin proves insufficient).
- **Predictability-aware horizon:** stop the forecast where the cloud exceeds a
  usefulness threshold (e.g. spread > X km) rather than a fixed time.

### P3 — Forecast quality for long drifts ("as good as possible")
- **Altitude/level drift:** the backtest found the *effective* float level deepens
  with lead (~290 → 350–400 hPa). The single-level cube is a real error source for
  long drifts. Evaluate a multi-level cube + vertical sampling, or a level schedule.
  (Touches cube schema + `sampleWind` — scope carefully.)
- **Seed the dead-reckon "now" uncertainty into the forward Monte Carlo** (issue #15
  item 2): the predicted-hindcast (fix→now) has its own growing uncertainty; sample
  the forward ensemble from that cloud rather than a single "now" point.

### Verification (every phase)
- Use `web/scripts/backtest/` to replay known long legs (e.g. the 5/19 → 5/29
  Gibraltar drift) with the new pipeline; score **miss distance** + **cone
  calibration** (does the 50/90% cloud contain the truth?) vs the current baseline.
- If reconstruction geometry changes, **bump `ALGO_VERSION`** (`hindcastStorage.ts`)
  so cached hindcasts recompute (see `hindcast-cache-algo-version` memory).

## 5. File-level change map

| Area | File | Change |
|---|---|---|
| Longitude wrap (P0) | `lib/wind/gfsGrid.ts` (`windAt`), `lib/wind/windCube.ts` (`sampleWind`), `lib/wind/balloonIntegrate.ts` | wrap lon into grid range; dateline-safe clamp |
| Truncate-on-exit + horizon cap (P0) | `lib/wind/balloonIntegrate.ts`, `lib/wind/monteCarloForecast.ts` | stop integrating outside coverage; cap `spanHours`/horizon |
| UI honesty (P0) | `components/dashboard-v2/V2MissionMap.tsx`, forecast consumers | cone/"uncertain" for very-stale; truncated path |
| Tube ingest (P1) | `scripts/gfs_ingest.py` | nominal pre-integration; per-slice windows; tube cube; lift 72 h cap for tube |
| Tube ensemble (P1/P2) | `scripts/gefs_ingest.py`, `scripts/aigefs_ingest.py` | per-member tube cubes |
| Cloud sizing / march (P2) | ingest + maybe `monteCarloForecast.ts` | window = ensemble cloud; optional march |
| Altitude / seed (P3) | cube schema, `sampleWind`, `monteCarloForecast.ts` | multi-level / level schedule; seed now-uncertainty |
| Verify | `scripts/backtest/*` | replay + score |
| Docs | `web/docs/forecast-architecture.md` | document the tube |

## 6. Risks / tradeoffs

- **GRIB messages are whole-globe on S3** (not spatially subsettable), so smaller
  boxes don't cut download — the tube's win is *coverage correctness + finer
  resolution*, not bandwidth. (NOMADS `grib-filter` could subset server-side — a
  separate lever if download matters.)
- **Sequential dependency:** P1 needs a nominal pass before fetching the tube; the
  full march (P2b) serializes fetch ↔ integrate. Start with the pre-integrated tube
  (keeps the clean Python-ingest / TS-compute split).
- **Very long gaps are intrinsically unpredictable** — beyond ~1–2 weeks even a
  perfect tube yields a globe-sized cloud. The honest answer there is the capped
  cone, not precision; don't over-engineer past the predictability limit.
- **Runtime** stays within the (now-fixed, continue-on-error) 28-min GEFS step / 50-min
  job; the tube is smaller per-slice but more sequential — measure.

## 7. Suggested PR sequencing
1. **PR-A (P0):** lon-wrap + truncate-on-exit + horizon cap + UI honesty. Self-contained,
   stops the live mirage. Ship first.
2. **PR-B (P1):** tube ingest for the forecast cube + backtest comparison.
3. **PR-C (P1):** tube for GEFS/AIGEFS member cubes.
4. **PR-D (P2):** ensemble-cloud window sizing + predictability horizon.
5. **PR-E (P3):** altitude/level realism + now-uncertainty seeding (ties into #15).

Relates to: issue #15 (improve forecasting); memories `gefs-ensemble-and-worker-compute`,
`balloon-forecast-backtest-findings`, `forecast-architecture-doc`, `hindcast-cache-algo-version`.
