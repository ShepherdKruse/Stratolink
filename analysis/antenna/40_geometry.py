"""PART A — Reception geometry for Stratolink-3: where, angularly, were we heard?

This is the foundation for the antenna study. It answers, from real flight data:
  - From what ELEVATION angles did ground gateways hear the balloon?
  - What DEPRESSION angle did the balloon's own antenna radiate into to reach
    them? (0deg = out the side / local horizon, 90deg = straight down / nadir.)
  - Over what DISTANCES, and in what AZIMUTHAL spread around the balloon?

GPS INTEGRITY GATE (Teddy's call, and it matters a lot):
  Flight-3 had the u-blox stale-fix bug (firmware/GPS_BUG_BOARD2.md). When the
  reported position is STALE, the balloon's true position is unknown, so any
  angle/distance computed from it is fiction. We classify every uplink
  (analysis/antenna/_gps.py) and compute geometry on FRESH fixes ONLY.
  We show the contamination explicitly (Plot A1) before discarding it.

Run:
  set -a; source ~/.config/stratolink/env; set +a   # only needed if re-fetching
  analysis/.venv/bin/python analysis/antenna/40_geometry.py
(Reads the cached telemetry_raw.parquet; no network needed.)
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

import _common as C
import _style as S
from _gps import classify_uplinks, summarize, LAUNCH_UTC


def as_list(v):
    """The `gateways` column is stored as a JSON string (sometimes a list/ndarray
    depending on the reader). Normalize to a list of dicts."""
    if isinstance(v, list):
        return v
    if isinstance(v, np.ndarray):
        return list(v)
    if isinstance(v, str) and v:
        try:
            return json.loads(v)
        except Exception:
            return []
    return []

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
FIGS = HERE / "figs"
FIGS.mkdir(exist_ok=True)

EARTH_R_KM = C.EARTH_R_KM


def bearing_deg(lat1, lon1, lat2, lon2) -> float:
    """Initial great-circle bearing (deg, 0=N, clockwise) from pt1 -> pt2."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def geometric_horizon_km(h_m: float, k: float = 1.0) -> float:
    """Geometric radio horizon (km) for a balloon at height h, gateway at sea
    level. k=1 geometric; k=4/3 standard-atmosphere refraction."""
    R = EARTH_R_KM * k
    h = h_m / 1000.0
    return R * math.acos(R / (R + h))


# ---------------------------------------------------------------------------
# Build the geolocated, GPS-classified reception table
# ---------------------------------------------------------------------------
def build_receptions() -> pd.DataFrame:
    tel = pd.read_parquet(DATA / "telemetry_raw.parquet")
    tel = classify_uplinks(tel)

    recs = []
    for _, r in tel.iterrows():
        gws = as_list(r["gateways"])
        if not gws:
            continue
        blat, blon, balt = r.get("lat"), r.get("lon"), r.get("altitude_m")
        for g in gws:
            if not isinstance(g, dict):
                continue
            recs.append({
                "time": r["time"],
                "device_id": r["device_id"],
                "region": r.get("region"),
                "gps_class": r["gps_class"],
                "balloon_lat": blat, "balloon_lon": blon, "balloon_alt": balt,
                "lora_sf": r.get("lora_sf"),
                "gateway_id": g.get("gateway_id"),
                "gw_lat": g.get("lat"), "gw_lon": g.get("lon"),
                "rssi": g.get("rssi"), "snr": g.get("snr"),
                "anonymized": C.is_anonymized(g.get("gateway_id")),
            })
    df = pd.DataFrame(recs)

    # Geometry only where we have BOTH a gateway position and a balloon position.
    has = (df["gw_lat"].notna() & df["gw_lon"].notna()
           & df["balloon_lat"].notna() & df["balloon_lon"].notna()
           & df["balloon_alt"].notna())
    df["has_coords"] = has

    def geom(row):
        if not row["has_coords"]:
            return pd.Series([np.nan]*5)
        gc = C.haversine_km(row["balloon_lat"], row["balloon_lon"], row["gw_lat"], row["gw_lon"])
        sl = C.slant_range_km(gc, row["balloon_alt"])
        el = C.elevation_angle_deg(gc, row["balloon_alt"])
        de = C.depression_angle_deg(gc, row["balloon_alt"])
        az = bearing_deg(row["balloon_lat"], row["balloon_lon"], row["gw_lat"], row["gw_lon"])
        return pd.Series([gc, sl, el, de, az])

    df[["gc_km", "slant_km", "elev_gw_deg", "depr_balloon_deg", "azimuth_deg"]] = df.apply(geom, axis=1)

    # Flight phase by balloon altitude: the fresh-fix sample is ascent-heavy, and
    # geometry differs by altitude (low alt -> near horizon, high elevation angles;
    # float -> gateways compressed to the horizon). Split so we don't conflate them.
    df["phase"] = np.where(df["balloon_alt"] >= 8000, "float", "ascent")
    return df, tel


# ---------------------------------------------------------------------------
# Plots
# ---------------------------------------------------------------------------
def plot_a1_integrity(df, fig_path):
    """Why we filter: the stale-fix contamination falls exactly on the
    long-range / below-horizon tail. Elevation angle vs slant range, geolocated
    receptions, colored FRESH vs STALE, with the geometric-horizon floor."""
    S.use_light()
    g = df[df["has_coords"]].copy()
    fresh = g[g["gps_class"] == "FRESH"]
    stale = g[g["gps_class"] == "STALE"]
    other = g[~g["gps_class"].isin(["FRESH", "STALE"])]

    fig, ax = plt.subplots(figsize=(11, 7))
    ax.axhspan(-5, 0, color=S.RED, alpha=0.07, zorder=0)
    ax.axhline(0, color=S.TEXT_DIM, lw=1.0, ls="--", zorder=1)
    ax.text(ax.get_xlim()[1] if False else 5, -2.4, "geometrically below horizon → impossible LOS",
            color=S.RED, fontsize=9, va="center")

    if len(other):
        ax.scatter(other["slant_km"], other["elev_gw_deg"], s=18, c=S.DIM,
                   alpha=0.5, label=f"other ({len(other)})", zorder=2)
    ax.scatter(fresh["slant_km"], fresh["elev_gw_deg"], s=22, c=S.TEAL7,
               alpha=0.8, edgecolors="none", label=f"FRESH fix ({len(fresh)})", zorder=4)
    ax.scatter(stale["slant_km"], stale["elev_gw_deg"], s=30, c=S.RED,
               alpha=0.85, marker="x", linewidths=1.4, label=f"STALE fix ({len(stale)})", zorder=5)

    # Flag the famous "433 km" reception if present (stale, below horizon).
    if len(stale):
        far = stale.loc[stale["slant_km"].idxmax()]
        ax.annotate(f"the “{far['slant_km']:.0f} km record”\n"
                    f"elev {far['elev_gw_deg']:.1f}°, RSSI {far['rssi']:.0f} dBm\n"
                    f"(computed vs a FROZEN position)",
                    xy=(far["slant_km"], far["elev_gw_deg"]),
                    xytext=(far["slant_km"]-150, far["elev_gw_deg"]+8),
                    color=S.RED, fontsize=9,
                    arrowprops=dict(arrowstyle="->", color=S.RED, lw=1.2))

    ax.set_xlabel("slant range balloon → gateway (km)")
    ax.set_ylabel("elevation angle at gateway (° above local horizon)")
    ax.set_title("A1 · GPS stale-fix contamination lands on the long-range tail\n"
                 "geolocated receptions — stale positions yield impossible below-horizon geometry")
    ax.legend(loc="upper right")
    ax.set_ylim(-5, max(38, g["elev_gw_deg"].max()+3))
    S.footer(fig, "Stratolink-3 · telemetry.gateways · geometry on geolocated receptions · analysis/antenna/40_geometry.py")
    fig.tight_layout()
    fig.savefig(fig_path, dpi=190)
    plt.close(fig)


def plot_a2_funnel(df, fig_path):
    """The angular funnel: at float altitude every gateway sits within a few
    degrees of the balloon's horizon. Theory curves (elev vs ground distance
    for several altitudes) + FRESH receptions colored by RSSI."""
    S.use_light()
    fresh = df[(df["gps_class"] == "FRESH") & df["has_coords"]].copy()

    fig, ax = plt.subplots(figsize=(11, 7))

    # Theory: elevation at gateway vs ground (great-circle) distance, per altitude.
    d = np.linspace(1, 460, 400)
    for h_km, col, lw in [(2, S.TEAL12, 1.3), (5, S.TEAL10, 1.5), (10, S.TEAL7, 2.2)]:
        elev = [C.elevation_angle_deg(dd, h_km*1000.0) for dd in d]
        ax.plot(d, elev, color=col, lw=lw, label=f"theory: balloon @ {h_km} km")
        # horizon marker
        hz = geometric_horizon_km(h_km*1000.0)
        ax.axvline(hz, color=col, ls=":", lw=1.0, alpha=0.6)
    ax.text(geometric_horizon_km(10000)+3, 30, "horizon @10 km\n(geometric 357 km;\n4/3-earth ~412 km)",
            color=S.TEAL7, fontsize=8.5, va="top")

    flo = fresh[fresh["phase"] == "float"]
    asc = fresh[fresh["phase"] == "ascent"]
    sc = ax.scatter(flo["gc_km"], flo["elev_gw_deg"], c=flo["rssi"],
                    cmap=S.RSSI_CMAP, vmin=S.RSSI_VMIN, vmax=S.RSSI_VMAX,
                    s=44, alpha=0.95, edgecolors=S.TEXT, linewidths=0.4, marker="o",
                    zorder=6, label=f"FRESH @ float ≥8 km (n={len(flo)})")
    ax.scatter(asc["gc_km"], asc["elev_gw_deg"], c=asc["rssi"],
               cmap=S.RSSI_CMAP, vmin=S.RSSI_VMIN, vmax=S.RSSI_VMAX,
               s=30, alpha=0.7, edgecolors="none", marker="^",
               zorder=5, label=f"FRESH @ ascent <8 km (n={len(asc)})")
    cb = fig.colorbar(sc, ax=ax, pad=0.015)
    cb.set_label("RSSI (dBm)")

    ax.axhline(0, color=S.TEXT_DIM, lw=0.8, ls="--")
    ax.set_xlabel("ground (great-circle) distance balloon → gateway (km)")
    ax.set_ylabel("elevation angle at gateway (°)")
    ax.set_title("A2 · The angular funnel: beyond ~50 km, every gateway sits within ~10° of the horizon\n"
                 "the long-range links that extend coverage are all near 0° — nadir energy is wasted")
    ax.set_xlim(0, 460)
    ax.set_ylim(-2, 42)
    ax.legend(loc="upper right")
    S.footer(fig, "Stratolink-3 · FRESH-fix geolocated receptions · analysis/antenna/40_geometry.py")
    fig.tight_layout()
    fig.savefig(fig_path, dpi=190)
    plt.close(fig)


def plot_a3_polar(df, fig_path):
    """Where around the balloon were we heard: azimuth (geographic bearing
    balloon->gateway) vs slant range, FRESH, colored by RSSI. The balloon spins
    freely, so azimuth is uncontrolled — this is why we need azimuthal omni."""
    S.use_light()
    fresh = df[(df["gps_class"] == "FRESH") & df["has_coords"]].copy()

    fig = plt.figure(figsize=(9.5, 9))
    ax = fig.add_subplot(111, projection="polar")
    ax.set_facecolor(S.PANEL)
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)  # clockwise = compass

    theta = np.deg2rad(fresh["azimuth_deg"].values)
    rr = fresh["slant_km"].values
    sc = ax.scatter(theta, rr, c=fresh["rssi"], cmap=S.RSSI_CMAP,
                    vmin=S.RSSI_VMIN, vmax=S.RSSI_VMAX, s=30, alpha=0.9, edgecolors="none")
    cb = fig.colorbar(sc, ax=ax, pad=0.10, shrink=0.7)
    cb.set_label("RSSI (dBm)")

    # horizon ring at 10 km
    hz = C.slant_range_km(geometric_horizon_km(10000), 10000)
    ax.plot(np.linspace(0, 2*np.pi, 200), [hz]*200, color=S.TEAL7, ls=":", lw=1.2)
    ax.text(np.deg2rad(45), hz+18, "10 km horizon", color=S.TEAL7, fontsize=8.5)

    ax.set_rlabel_position(112.5)
    ax.set_xticklabels(["N", "NE", "E", "SE", "S", "SW", "W", "NW"], color=S.TEXT_DIM)
    ax.set_title("A3 · Azimuthal spread of receptions (bearing balloon → gateway)\n"
                 "radius = slant range (km) · the balloon spins freely, so azimuth is uncontrolled → omni needed",
                 pad=24)
    S.footer(fig, "Stratolink-3 · FRESH-fix geolocated receptions · analysis/antenna/40_geometry.py")
    fig.tight_layout()
    fig.savefig(fig_path, dpi=190)
    plt.close(fig)


def plot_a4_antenna_view(df, fig_path):
    """What the balloon antenna actually had to illuminate: depression-angle
    distribution (0deg=horizon, 90deg=nadir), FRESH only, split ASCENT vs FLOAT.
    This is the direct design input for Part B pattern modeling.

    Why the split: the fresh-fix sample is ascent-heavy (the clean SF climb), and
    at low altitude the horizon is near so gateways appear at HIGHER elevation.
    At float (>=8 km, the operational condition) geometry compresses gateways to
    the horizon. Conflating them would overstate the high-angle tail."""
    S.use_light()
    fresh = df[(df["gps_class"] == "FRESH") & df["has_coords"]].copy()
    asc = fresh[fresh["phase"] == "ascent"]["depr_balloon_deg"].dropna().values
    flo = fresh[fresh["phase"] == "float"]["depr_balloon_deg"].dropna().values
    alld = fresh["depr_balloon_deg"].dropna().values

    fig, ax = plt.subplots(figsize=(11.5, 6.8))
    bins = np.arange(0, 46, 2.5)
    ax.hist([flo, asc], bins=bins, stacked=True,
            color=[S.TEAL7, S.DIM], edgecolor=S.BG, linewidth=0.6,
            label=[f"FLOAT ≥8 km (n={len(flo)}) — operational", f"ascent <8 km (n={len(asc)})"])
    ax.set_xlabel("depression angle below balloon's local horizontal (°)   "
                  "[0° = out the side, 90° = straight down]")
    ax.set_ylabel("reception count")

    ax2 = ax.twinx()
    for d, col, lab in [(flo, S.MINT, "float CDF"), (alld, S.WARM, "all-fresh CDF")]:
        if len(d) > 1:
            xs = np.sort(d); cdf = np.arange(1, len(xs)+1)/len(xs)*100
            ax2.plot(xs, cdf, color=col, lw=2.0, label=lab)
    ax2.set_ylabel("cumulative % of receptions", color=S.WARM)
    ax2.tick_params(axis="y", labelcolor=S.WARM)
    ax2.set_ylim(0, 100); ax2.grid(False)

    if len(flo):
        f10 = (flo <= 10).mean()*100
        ax2.axvline(10, color=S.MINT, ls="--", lw=1.0, alpha=0.7)
        ax.text(10.4, ax.get_ylim()[1]*0.7,
                f"at FLOAT: {f10:.0f}% of receptions\nwithin 10° of horizontal\n(median {np.median(flo):.1f}°)",
                color=S.MINT, fontsize=9.5)

    ax.set_title("A4 · What the balloon antenna had to illuminate (FRESH-fix receptions, ~all at float)\n"
                 "median 8° below horizon, half within 10°; tail to 40° = nearby gateways. Nadir never used.")
    ax.set_xlim(0, 45)
    h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1+h2, l1+l2, loc="upper right")
    S.footer(fig, "Stratolink-3 · FRESH-fix geolocated receptions · input to Part B pattern modeling")
    fig.tight_layout()
    fig.savefig(fig_path, dpi=190)
    plt.close(fig)


# ---------------------------------------------------------------------------
def report(df, tel):
    def block(title): print("\n" + "="*72 + f"\n{title}\n" + "="*72)

    block("GPS classification (post-launch uplinks)")
    s = summarize(tel)
    print(f"post-launch uplinks: {s['post_launch_uplinks']}")
    for k in ("stratolink-3", "stratolink-3-eu", "ALL"):
        if k in s: print(f"  {k:18} {s[k]}")

    block("Receptions: total vs geolocated vs FRESH-geolocated")
    n_all = len(df)
    n_geo = int(df["has_coords"].sum())
    geo = df[df["has_coords"]]
    n_fresh = int(((df["gps_class"]=="FRESH") & df["has_coords"]).sum())
    n_stale = int(((df["gps_class"]=="STALE") & df["has_coords"]).sum())
    print(f"all receptions:            {n_all}")
    print(f"geolocated (gw+balloon):   {n_geo}")
    print(f"  of which FRESH fix:      {n_fresh}   <- geometry uses THESE")
    print(f"  of which STALE fix:      {n_stale}   <- discarded (position fiction)")
    print(f"  other class:             {n_geo-n_fresh-n_stale}")

    block("Headline geometry: ALL-geolocated vs FRESH-only (the contamination delta)")
    for name, sub in [("ALL geolocated", geo), ("FRESH only", geo[geo['gps_class']=='FRESH'])]:
        if not len(sub): continue
        print(f"\n[{name}]  n={len(sub)}")
        print(f"  slant range  km : median {sub['slant_km'].median():6.1f}   max {sub['slant_km'].max():6.1f}")
        print(f"  gc distance  km : median {sub['gc_km'].median():6.1f}   max {sub['gc_km'].max():6.1f}")
        print(f"  elev @ gw   deg : median {sub['elev_gw_deg'].median():6.1f}   min {sub['elev_gw_deg'].min():6.1f}   max {sub['elev_gw_deg'].max():6.1f}")
        print(f"  depr balloon deg: median {sub['depr_balloon_deg'].median():6.1f}   min {sub['depr_balloon_deg'].min():6.1f}   max {sub['depr_balloon_deg'].max():6.1f}")
        below = (sub['elev_gw_deg'] < 0).sum()
        print(f"  below-horizon (elev<0): {below}  ({100*below/len(sub):.1f}%)")

    fresh_geo = geo[geo['gps_class']=='FRESH']
    if len(fresh_geo):
        block("FRESH-only angular concentration, by flight phase (design-relevant)")
        for ph in ("float", "ascent", "all"):
            sub = fresh_geo if ph == "all" else fresh_geo[fresh_geo["phase"]==ph]
            if not len(sub): continue
            dep = sub['depr_balloon_deg']; ele = sub['elev_gw_deg']
            print(f"\n  [{ph}]  n={len(sub)}  (balloon alt median {sub['balloon_alt'].median():.0f} m)")
            print(f"    depression: median {dep.median():4.1f}deg  |  within 10deg {100*(dep<=10).mean():4.0f}%  within 5deg {100*(dep<=5).mean():4.0f}%  max {dep.max():4.1f}deg")
            print(f"    gw elev:    median {ele.median():4.1f}deg  |  <=10deg {100*(ele<=10).mean():4.0f}%  max {ele.max():4.1f}deg")
            print(f"    slant range: median {sub['slant_km'].median():5.1f} km  max {sub['slant_km'].max():5.1f} km")
        far = fresh_geo.loc[fresh_geo['slant_km'].idxmax()]
        print(f"\n  longest FRESH reception: slant {far['slant_km']:.0f} km, gc {far['gc_km']:.0f} km, "
              f"elev {far['elev_gw_deg']:.1f}deg, RSSI {far['rssi']:.0f} dBm, alt {far['balloon_alt']:.0f} m ({far['phase']})")
        # azimuthal uniformity check (Rayleigh-style): is reception spread all around?
        az = np.deg2rad(fresh_geo['azimuth_deg'].dropna().values)
        if len(az):
            Rbar = np.hypot(np.cos(az).mean(), np.sin(az).mean())
            print(f"  azimuthal concentration |R| = {Rbar:.2f} (0=uniform all-around, 1=one direction); "
                  f"n_az={len(az)}")


def main():
    df, tel = build_receptions()
    df.to_parquet(DATA / "receptions_geo.parquet")
    df.to_csv(DATA / "receptions_geo.csv", index=False)
    report(df, tel)

    print("\nrendering plots...")
    plot_a1_integrity(df, FIGS / "A1_gps_contamination.png");   print("  A1_gps_contamination.png")
    plot_a2_funnel(df, FIGS / "A2_angular_funnel.png");          print("  A2_angular_funnel.png")
    plot_a3_polar(df, FIGS / "A3_azimuth_polar.png");            print("  A3_azimuth_polar.png")
    plot_a4_antenna_view(df, FIGS / "A4_antenna_view.png");      print("  A4_antenna_view.png")
    print("done.")


if __name__ == "__main__":
    main()
