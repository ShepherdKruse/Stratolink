"""24-hour Stratolink-3 forecast over Iberia + Morocco + W. Sahara.

Minimal-chrome render: bleed-to-edges map, no title or description, a tiny key
in the corner. Visual scheme:
  • cream solid line   = observed past trajectory (matches the transatlantic render)
  • white dot          = last GPS ping (Málaga, May 29 17:46 UTC)
  • amber filled cone  = 50 % confidence envelope swept across the 24 h horizon
  • amber dashed cone  = 90 % confidence envelope
  • bright amber line  = nominal Monte Carlo trajectory through the cone

Wind data: latest available NOAA GFS cycles from the AWS S3 open-data bucket,
selected freshest-first relative to the current wall-clock UTC (`now_utc`).
The full forecast window [last_fix, last_fix + 24 h] is stitched from
multiple cycles so every hour gets the freshest possible forecast skill.
"""
from __future__ import annotations

import os, sys, math
from pathlib import Path
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd
import requests
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D

import cartopy.crs as ccrs
import cartopy.feature as cfeature
from shapely.geometry import Polygon
from shapely.ops import unary_union

# Wire up Shepherd & Caleb's NOAA predictor module
_SIM_DIR = Path(__file__).resolve().parents[2] / "simulation"
if str(_SIM_DIR) not in sys.path:
    sys.path.insert(0, str(_SIM_DIR))
from predictor.weather import gfs_client
from predictor.weather.wind_field import RegularGridWindField
import xarray as xr

# Reuse the GFS multi-cycle fetcher + RK4 advection from the main script
sys.path.insert(0, str(Path(__file__).resolve().parent))
from transatlantic_path import fetch_gfs_wind_field, advect_single, wind_at  # noqa: E402

SBKEY = os.environ.get("SBKEY")
SBURL = "https://iazmnyyfsobucndqncgw.supabase.co"
OUT_PNG = Path(__file__).parent / "forecast_iberia.png"

# ---- Map extent: landscape rectangle, Iberia + Morocco + W. Sahara + a slice
# of Atlantic to give the forecast cone breathing room without dominant ocean.
LON_MIN, LON_MAX = -16.0, 8.0    # 24° wide
LAT_MIN, LAT_MAX = 21.0, 45.0    # 24° tall - almost square but landscape figure
# (aspect ratio is set by figsize, not the extent)

# Wind backdrop sampling resolution
BACKDROP_LON_STEP = 0.4
BACKDROP_LAT_STEP = 0.4
BACKDROP_PRESSURE_HPA = 300.0

# Ensemble parameters - beefier than the JS prod default for smoother ellipses
N_ENSEMBLE = 2000            # robust statistics over a 24 h horizon
FORECAST_HOURS = 24
STEP_MINUTES = 10
SPEED_SIGMA = 0.10
DIR_SIGMA_DEG = 12.0
ALT_SIGMA_M = 100.0
NOMINAL_ALT_M = 10000.0

# Hourly ellipse times - used to compute, but only labeled hours are RENDERED.
ELLIPSE_HOURS = list(range(1, FORECAST_HOURS + 1))
HOUR_LABEL_HOURS = (6, 12, 18, 24)   # discrete ellipse pairs at these horizons

# ---- Visual palette ---------------------------------------------------------
OBSERVED_COLOR = (0.98, 0.94, 0.86, 1.0)   # cream - same as transatlantic line
FORECAST_FILL = "#faefdb"                   # cream (same as the original path)
FORECAST_LINE = "#fff6e1"                   # brighter cream for the nominal stroke
MAP_BG = "#0a0a14"                          # map interior (no figure-level fill)
WIND_PALETTE = [
    (0.04, 0.08, 0.18), (0.07, 0.18, 0.40), (0.08, 0.40, 0.55),
    (0.18, 0.65, 0.50), (0.42, 0.82, 0.38), (0.86, 0.88, 0.20),
    (0.98, 0.60, 0.10), (0.95, 0.25, 0.18), (0.85, 0.20, 0.55),
    (0.75, 0.40, 0.85),
]


# ---- data fetch -------------------------------------------------------------

def fetch_track() -> pd.DataFrame:
    r = requests.get(
        f"{SBURL}/rest/v1/telemetry",
        params={
            "device_id": "in.(stratolink-3,stratolink-3-eu)",
            "select": "time,device_id,lat,lon,altitude_m,pressure",
            "order": "time.asc",
            "limit": "5000",
        },
        headers={"apikey": SBKEY, "Authorization": f"Bearer {SBKEY}"},
        timeout=30,
    )
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    df["time"] = pd.to_datetime(df["time"], utc=True, format="ISO8601")
    df = df[df["lat"].notna() & df["lon"].notna() & (df["altitude_m"] > 1000)]
    df = df.sort_values("time").reset_index(drop=True)
    keep = []; last = None
    for _, row in df.iterrows():
        cur = (round(row["lat"], 6), round(row["lon"], 6), int(row["altitude_m"]))
        if last is None or cur != last:
            keep.append(True); last = cur
        else:
            keep.append(False)
    return df[keep].reset_index(drop=True)


# ---- ellipse math (port of Shepherd & Caleb's `computeEllipse`) -------------

def compute_ellipse(positions: np.ndarray, confidence: float) -> dict:
    """2-D Gaussian confidence ellipse around the mean of `(lon, lat)` points.

    Eigendecomposes the local-tangent-plane covariance and scales the semi-axes
    by sqrt(chi2(2-dof, q)) so the polygon contains ~`confidence` fraction of
    a bivariate normal. χ²(0.5) = 1.386, χ²(0.9) = 4.605.
    """
    chi2 = {0.5: 1.386, 0.9: 4.605}.get(confidence,
                                          float(-2.0 * math.log(1.0 - confidence)))
    mean_lon = float(positions[:, 0].mean())
    mean_lat = float(positions[:, 1].mean())
    cos_lat = math.cos(math.radians(mean_lat))
    xs = (positions[:, 0] - mean_lon) * 111.32 * cos_lat
    ys = (positions[:, 1] - mean_lat) * 111.32
    sxx = float(np.mean(xs * xs))
    syy = float(np.mean(ys * ys))
    sxy = float(np.mean(xs * ys))
    tr, det = sxx + syy, sxx * syy - sxy * sxy
    disc = max(0.0, (tr * tr) / 4.0 - det)
    l1 = tr / 2.0 + math.sqrt(disc)
    l2 = tr / 2.0 - math.sqrt(disc)
    a_km = math.sqrt(max(0.0, l1) * chi2)
    b_km = math.sqrt(max(0.0, l2) * chi2)
    theta = 0.5 * math.atan2(2.0 * sxy, sxx - syy)
    N_VERT = 96   # smoother boundary for nicer rendering
    t = np.linspace(0.0, 2.0 * math.pi, N_VERT + 1)
    xe = a_km * np.cos(t)
    ye = b_km * np.sin(t)
    xr = xe * math.cos(theta) - ye * math.sin(theta)
    yr = xe * math.sin(theta) + ye * math.cos(theta)
    poly_lon = mean_lon + xr / (111.32 * cos_lat)
    poly_lat = mean_lat + yr / 111.32
    return {
        "center": (mean_lon, mean_lat),
        "semi_a_km": a_km, "semi_b_km": b_km,
        "theta_deg": math.degrees(theta),
        "polygon_lon": poly_lon, "polygon_lat": poly_lat,
    }


def run_forecast_ensemble(
    wf, start_pos, start_time, altitude_m,
    duration_hours: float = FORECAST_HOURS,
    step_minutes: int = STEP_MINUTES,
    n_members: int = N_ENSEMBLE,
    seed: int = 20260530,
) -> dict:
    """Monte Carlo forecast - per-member speed/direction/altitude perturbations.

    Returns a dict with `nominal_lons/lats`, `member_lons/lats` (N × Hours+1),
    and an `ellipses` list with `e50` and `e90` polygons for each hour 1..H.
    """
    rng = np.random.default_rng(seed)
    end_time = start_time + timedelta(hours=duration_hours)
    n_out = int(duration_hours) + 1
    out_hours = np.arange(n_out, dtype=float)
    member_lons = np.full((n_members, n_out), np.nan)
    member_lats = np.full((n_members, n_out), np.nan)

    try:
        from predictor.atmosphere import isa
    except Exception:
        isa = None

    print(f"  forecasting {n_members} members × {duration_hours:.0f}h from "
          f"({start_pos[0]:.3f}, {start_pos[1]:.3f}) at {start_time.isoformat()[:19]} UTC", flush=True)

    for k in range(n_members):
        speed_mult = 1.0 + SPEED_SIGMA * float(rng.normal())
        dir_off_rad = math.radians(DIR_SIGMA_DEG * float(rng.normal()))
        alt_off = ALT_SIGMA_M * float(rng.normal())
        member_alt = altitude_m + alt_off
        cos_d, sin_d = math.cos(dir_off_rad), math.sin(dir_off_rad)
        p_hpa = (isa.pressure(member_alt) / 100.0) if isa else 300.0
        schedule = (lambda _t, _p=p_hpa: _p)

        def _wind_at(_wf, t, lat, lon, p_hpa_q, noise_u=0.0, noise_v=0.0):
            u0, v0 = wind_at(_wf, t, lat, lon, p_hpa_q)
            u1 = (u0 * cos_d - v0 * sin_d) * speed_mult
            v1 = (u0 * sin_d + v0 * cos_d) * speed_mult
            return float(u1) + float(noise_u), float(v1) + float(noise_v)

        import transatlantic_path as _tp
        _orig = _tp.wind_at
        _tp.wind_at = _wind_at
        try:
            path = advect_single(wf, start_pos, start_time, end_time, schedule,
                                  dt_minutes=step_minutes)
        finally:
            _tp.wind_at = _orig

        times = [p[0] for p in path]
        lats = np.array([p[1] for p in path])
        lons = np.array([p[2] for p in path])
        t_secs = np.array([(t - start_time).total_seconds() for t in times])
        out_secs = out_hours * 3600.0
        member_lons[k] = np.interp(out_secs, t_secs, lons)
        member_lats[k] = np.interp(out_secs, t_secs, lats)

        if (k + 1) % 250 == 0:
            print(f"    {k+1}/{n_members}", flush=True)

    print(f"  ensemble complete", flush=True)

    # Nominal (deterministic) trajectory
    schedule_nom = (lambda _t, _p=300.0: _p)
    nominal = advect_single(wf, start_pos, start_time, end_time, schedule_nom,
                              dt_minutes=step_minutes)
    nom_t = np.array([(p[0] - start_time).total_seconds() for p in nominal])
    nom_lon = np.interp(out_hours * 3600.0, nom_t, np.array([p[2] for p in nominal]))
    nom_lat = np.interp(out_hours * 3600.0, nom_t, np.array([p[1] for p in nominal]))

    # Per-hour ellipses (every hour 1..H, so the swept cone is smooth)
    ellipses = []
    for h in ELLIPSE_HOURS:
        pos = np.column_stack([member_lons[:, h], member_lats[:, h]])
        pos = pos[np.isfinite(pos).all(axis=1)]
        if len(pos) < 5:
            continue
        ellipses.append({
            "t_hours": h,
            "e50": compute_ellipse(pos, 0.5),
            "e90": compute_ellipse(pos, 0.9),
        })

    return {
        "out_hours": out_hours,
        "member_lons": member_lons, "member_lats": member_lats,
        "nominal_lons": nom_lon, "nominal_lats": nom_lat,
        "ellipses": ellipses,
        "start_pos": start_pos, "start_time": start_time, "end_time": end_time,
    }


# ---- wind backdrop ----------------------------------------------------------

def build_backdrop_grid(wf, t_sample: datetime, pressure_hpa: float = BACKDROP_PRESSURE_HPA):
    lats = np.arange(LAT_MIN, LAT_MAX + BACKDROP_LAT_STEP, BACKDROP_LAT_STEP)
    lons = np.arange(LON_MIN, LON_MAX + BACKDROP_LON_STEP, BACKDROP_LON_STEP)
    U = np.zeros((len(lats), len(lons)), dtype=np.float32)
    V = np.zeros_like(U)
    for j, la in enumerate(lats):
        for i, lo in enumerate(lons):
            u, v = wf.get_wind(lat=float(la), lon=float(lo),
                                pressure_pa=float(pressure_hpa) * 100.0,
                                time=t_sample)
            U[j, i] = u
            V[j, i] = v
    return lons, lats, U, V, np.sqrt(U * U + V * V)


# ---- plotting ---------------------------------------------------------------

def plot(observed_track: pd.DataFrame, last_fix: dict, forecast: dict,
         backdrop, now_utc: datetime, gfs_meta: str):
    # Landscape figure, no facecolor so we don't paint a black border
    fig = plt.figure(figsize=(16, 10), facecolor="none")
    proj = ccrs.PlateCarree(central_longitude=(LON_MIN + LON_MAX) / 2)
    # Full-bleed: axes fills the entire figure rectangle, no padding
    ax = fig.add_axes([0.0, 0.0, 1.0, 1.0], projection=proj)
    ax.set_extent([LON_MIN, LON_MAX, LAT_MIN, LAT_MAX], crs=ccrs.PlateCarree())
    ax.set_facecolor(MAP_BG)

    # ---- Wind backdrop (muted so the forecast cone reads cleanly) ---------
    lons, lats, U, V, S = backdrop
    LON_grid, LAT_grid = np.meshgrid(lons, lats)
    wind_cmap = mcolors.LinearSegmentedColormap.from_list("wind", WIND_PALETTE, N=512)
    ax.pcolormesh(LON_grid, LAT_grid, S,
                   cmap=wind_cmap, vmin=0, vmax=45,
                   shading="gouraud", transform=ccrs.PlateCarree(),
                   zorder=1, alpha=0.28)
    ax.streamplot(LON_grid, LAT_grid, U, V,
                   density=2.4, linewidth=0.4,
                   color=(0.55, 0.70, 0.95, 0.20), arrowsize=0,
                   transform=ccrs.PlateCarree(), zorder=2)

    # ---- Coastlines + borders (also softened) -----------------------------
    ax.add_feature(cfeature.COASTLINE.with_scale("10m"),
                   linewidth=0.9, edgecolor=(0.88, 0.90, 0.96, 0.75), zorder=3)
    ax.add_feature(cfeature.BORDERS.with_scale("10m"),
                   linewidth=0.5, edgecolor=(0.78, 0.82, 0.90, 0.40), zorder=3)

    # ---- Spaghetti underlay: every Nth ensemble trajectory in faint cream
    # lines. Streamlines now use a cool blue tone so the cream spaghetti
    # reads as a clearly distinct overlay.
    m_lons = forecast["member_lons"]
    m_lats = forecast["member_lats"]
    n_total = m_lons.shape[0]
    stride = max(1, n_total // 350)
    for k in range(0, n_total, stride):
        ax.plot(m_lons[k], m_lats[k],
                color=FORECAST_FILL, linewidth=0.55, alpha=0.12,
                solid_capstyle="round",
                transform=ccrs.PlateCarree(), zorder=5)

    # ---- Discrete confidence ellipses ONLY at labeled horizons ------------
    # e90 dashed outlines (drawn first so e50 layers above).
    for h in HOUR_LABEL_HOURS:
        e = next((x for x in forecast["ellipses"] if x["t_hours"] == h), None)
        if not e: continue
        ax.plot(e["e90"]["polygon_lon"], e["e90"]["polygon_lat"],
                color=FORECAST_FILL, linewidth=1.5, alpha=0.75,
                linestyle=(0, (5, 4)),
                transform=ccrs.PlateCarree(), zorder=6)

    # e50 filled + solid outlined.
    for h in HOUR_LABEL_HOURS:
        e = next((x for x in forecast["ellipses"] if x["t_hours"] == h), None)
        if not e: continue
        ax.fill(e["e50"]["polygon_lon"], e["e50"]["polygon_lat"],
                color=FORECAST_FILL, alpha=0.22,
                transform=ccrs.PlateCarree(), zorder=7)
        ax.plot(e["e50"]["polygon_lon"], e["e50"]["polygon_lat"],
                color=FORECAST_FILL, linewidth=1.9, alpha=0.95,
                transform=ccrs.PlateCarree(), zorder=8)

    # ---- Recent observed track in cream (matches the transatlantic look) --
    obs_recent = observed_track[observed_track["time"] >=
                                  (last_fix["time"] - pd.Timedelta(hours=48))]
    if len(obs_recent) >= 2:
        # Single bright cream stroke, no glow
        ax.plot(obs_recent["lon"].values, obs_recent["lat"].values,
                color=OBSERVED_COLOR, linewidth=2.4,
                solid_capstyle="round", solid_joinstyle="round",
                transform=ccrs.PlateCarree(), zorder=9)

    # ---- Nominal forecast trajectory (bright amber line on top of cone) ----
    ax.plot(forecast["nominal_lons"], forecast["nominal_lats"],
            color=FORECAST_LINE, linewidth=2.6, alpha=1.0,
            solid_capstyle="round", solid_joinstyle="round",
            transform=ccrs.PlateCarree(), zorder=10)

    # ---- Last-position marker (white) -------------------------------------
    ax.scatter([last_fix["lon"]], [last_fix["lat"]],
               s=160, c="white", marker="o",
               edgecolors=(0.10, 0.10, 0.14, 0.95), linewidths=1.4,
               transform=ccrs.PlateCarree(), zorder=12)

    # ---- Hour labels: anchored to the EAST edge of each e90 ellipse so
    # each label sits beside (not inside) its corresponding ring -----------
    for h in HOUR_LABEL_HOURS:
        e = next((x for x in forecast["ellipses"] if x["t_hours"] == h), None)
        if not e: continue
        # East-most point on the e90 outline (visually outside both rings).
        poly_lon = np.array(e["e90"]["polygon_lon"])
        poly_lat = np.array(e["e90"]["polygon_lat"])
        idx_e = int(np.argmax(poly_lon))
        anchor_lon = float(poly_lon[idx_e])
        anchor_lat = float(poly_lat[idx_e])
        if not (LON_MIN <= anchor_lon <= LON_MAX and LAT_MIN <= anchor_lat <= LAT_MAX):
            continue
        # Small dot at the ellipse center (where nominal trajectory passes
        # through) - anchors the label to a precise time point.
        cx = float(e["e50"]["center"][0])
        cy = float(e["e50"]["center"][1])
        ax.scatter([cx], [cy], s=28, c=[FORECAST_LINE],
                    edgecolors=(0.10, 0.10, 0.14, 0.8), linewidths=0.9,
                    transform=ccrs.PlateCarree(), zorder=11)
        ax.annotate(f"+{h}h",
                      xy=(anchor_lon, anchor_lat),
                      xytext=(8, 0), textcoords="offset points",
                      color="#f8f3e6", fontsize=11.5, fontweight="medium",
                      ha="left", va="center",
                      xycoords=ccrs.PlateCarree()._as_mpl_transform(ax),
                      zorder=12)

    # No key, no colorbar, no provenance stamp - just the map.
    plt.savefig(OUT_PNG, dpi=240, bbox_inches=None, pad_inches=0,
                facecolor="none")
    print(f"  wrote {OUT_PNG}")


def main():
    if not SBKEY: sys.exit("Set SBKEY")
    print("[1/4] Fetching track...")
    track = fetch_track()
    last = track.iloc[-1]
    last_fix = {
        "lat": float(last["lat"]),
        "lon": float(last["lon"]),
        "altitude_m": float(last["altitude_m"]),
        "time": last["time"].to_pydatetime().replace(tzinfo=timezone.utc),
    }
    now_utc = datetime.now(timezone.utc)
    print(f"  last ping: {last_fix['time'].isoformat()[:19]} UTC at "
          f"{last_fix['lat']:.3f}°N {last_fix['lon']:.3f}°W, alt {last_fix['altitude_m']:.0f}m")
    print(f"  now: {now_utc.isoformat()[:19]} UTC "
          f"({(now_utc - last_fix['time']).total_seconds()/3600:.1f}h after last ping)")

    print("[2/4] Fetching latest GFS cycles for the forecast window...")
    fc_start = last_fix["time"]
    fc_end = fc_start + timedelta(hours=FORECAST_HOURS + 4)
    wf = fetch_gfs_wind_field(
        start_time=fc_start,
        end_time=fc_end,
        altitude_m=NOMINAL_ALT_M,
        lat_min=LAT_MIN - 4.0, lat_max=LAT_MAX + 4.0,
        lon_min=LON_MIN - 4.0, lon_max=LON_MAX + 4.0,
        cache_dir=Path.home() / ".cache" / "stratolink" / "predictor",
        now_utc=now_utc,
    )
    # Describe which cycle was the freshest one we used
    gfs_meta = "multi-cycle (freshest as of now)"

    print(f"[3/4] Running forecast ensemble ({N_ENSEMBLE} members)...")
    forecast = run_forecast_ensemble(
        wf=wf,
        start_pos=(last_fix["lat"], last_fix["lon"]),
        start_time=fc_start,
        altitude_m=last_fix["altitude_m"] or NOMINAL_ALT_M,
        n_members=N_ENSEMBLE,
    )
    # Summary of the labeled hours only
    print("  per-hour forecast (labeled only):")
    for e in forecast["ellipses"]:
        if e["t_hours"] not in HOUR_LABEL_HOURS:
            continue
        e50 = e["e50"]; e90 = e["e90"]
        print(f"  +{e['t_hours']:>2}h  center=({e50['center'][1]:6.3f}°N, "
              f"{abs(e50['center'][0]):6.3f}°W)  e50 axes {e50['semi_a_km']:>4.0f}×{e50['semi_b_km']:<3.0f}km  "
              f"e90 axes {e90['semi_a_km']:>4.0f}×{e90['semi_b_km']:<3.0f}km")

    print("[4/4] Building backdrop + rendering...")
    backdrop = build_backdrop_grid(wf, fc_start)
    plot(track, last_fix, forecast, backdrop, now_utc, gfs_meta)


if __name__ == "__main__":
    main()
