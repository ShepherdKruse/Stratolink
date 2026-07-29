"""Empirical TX-range audit for Stratolink-3.

For every uplink that has BOTH a balloon GPS fix AND identifiable gateway
positions (either inline in `gateways` JSONB or via TTN-Mapper cross-reference),
compute the great-circle distance, then compare against:
  - Geometric radio horizon at the balloon's altitude
  - 4/3-Earth refraction-corrected horizon
  - Link-budget-limited free-space max range (given RSSI / TX gain)
  - LoRa world records (TTN 702 km, SODAQ 354 km @ 15 km altitude)
"""
from __future__ import annotations

import os, sys, math, json
from pathlib import Path
import numpy as np
import pandas as pd
import requests
import matplotlib.pyplot as plt

SBKEY = os.environ.get("SBKEY")
SBURL = "https://iazmnyyfsobucndqncgw.supabase.co"
CACHE_DIR = Path.home() / ".cache" / "stratolink"

# Physical constants
EARTH_R_KM = 6371.0
K_REFRACT = 4.0 / 3.0
LIGHT_C = 299_792_458.0

# Link-budget model (worst-case)
TX_POWER_DBM = 20.0
TX_GAIN_DBI = 1.0       # current monopole on small GP, conservative
RX_GAIN_DBI = 3.0       # typical TTN gateway omni
POL_LOSS_DB = 3.0       # avg linear-linear with random orientation
NF_DB = 6.0
SNR_LIM_SF7 = -7.5      # Semtech datasheet for SF7
BW = 125_000

OUT_PNG = Path(__file__).parent / "range_audit.png"


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km."""
    p = math.pi / 180.0
    a = (0.5 - math.cos((lat2 - lat1) * p) / 2
         + math.cos(lat1 * p) * math.cos(lat2 * p)
         * (1 - math.cos((lon2 - lon1) * p)) / 2)
    return 2 * EARTH_R_KM * math.asin(math.sqrt(a))


def radio_horizon_km(alt_m, k=K_REFRACT):
    h = alt_m / 1000.0
    Re = k * EARTH_R_KM
    return math.sqrt(2 * Re * h + h * h)


def fspl_db(d_km, f_mhz=915.0):
    return 32.45 + 20 * math.log10(d_km) + 20 * math.log10(f_mhz)


def sx1262_sensitivity_dbm(sf=7, bw=BW, nf=NF_DB):
    """SX1262 sensitivity for given SF/BW assuming NF=6 dB."""
    thermal = -174 + 10 * math.log10(bw)
    snr_lim = {7: -7.5, 8: -10, 9: -12.5, 10: -15, 11: -17.5, 12: -20}[sf]
    return thermal + nf + snr_lim


def link_budget_max_range_km(rssi_target_dbm=-123.0, f_mhz=915.0,
                              tx_dbm=TX_POWER_DBM, gtx=TX_GAIN_DBI,
                              grx=RX_GAIN_DBI, pol=POL_LOSS_DB):
    """Max range at which RSSI ≥ target, given the link budget."""
    # RSSI = TX + Gtx - FSPL - pol + Grx → FSPL_max = TX + Gtx + Grx - pol - RSSI_target
    fspl_max = tx_dbm + gtx + grx - pol - rssi_target_dbm
    log_d = (fspl_max - 32.45 - 20 * math.log10(f_mhz)) / 20
    return 10 ** log_d


def fetch_all():
    url = f"{SBURL}/rest/v1/telemetry"
    params = {
        "device_id": "eq.stratolink-3",
        "select": "time,lat,lon,altitude_m,pressure,rssi,snr,lora_sf,gateways",
        "order": "time.asc",
        "limit": "5000",
    }
    h = {"apikey": SBKEY, "Authorization": f"Bearer {SBKEY}"}
    r = requests.get(url, params=params, headers=h, timeout=30)
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    df["time"] = pd.to_datetime(df["time"], utc=True, format="ISO8601")
    return df


def load_gateway_db():
    """Use the cached PB Mapper / TTN gateway location list."""
    csv = CACHE_DIR / "ttn_gateways.csv"
    if not csv.exists():
        print("  WARNING: no cached gateway CSV; gateway lookups will be limited to inline data")
        return None
    gw = pd.read_csv(csv)
    gw = gw.dropna(subset=["lat", "lon"])
    gw["id"] = gw["id"].astype(str)
    # Build a dict by lowercase ID for case-insensitive lookup
    return {str(r["id"]).lower(): (r["lat"], r["lon"]) for _, r in gw.iterrows()}


def extract_receptions(df, gw_db):
    """Yield (time, balloon_lat, balloon_lon, balloon_alt, gw_id, gw_lat, gw_lon,
              rssi, snr, sf, distance_km).
    Filters: only fresh GPS rows (not from stale-fix bursts) AND only real
    gateway IDs (not 'packetbroker' placeholder)."""
    # Detect stale-GPS rows: bit-identical (lat, lon, alt, sats) to prior fresh fix
    df = df.copy().reset_index(drop=True)
    df["stale"] = False
    last_fresh = None
    for i, r in df.iterrows():
        if pd.isna(r["lat"]):
            continue
        cur = (round(r["lat"], 6), round(r["lon"], 6), int(r["altitude_m"]))
        if last_fresh is not None and cur == last_fresh:
            df.at[i, "stale"] = True
        else:
            last_fresh = cur

    PLACEHOLDER_IDS = {"packetbroker", "", "unknown"}
    rows = []
    skipped_stale = 0
    skipped_placeholder = 0
    skipped_no_pos = 0
    for _, r in df.iterrows():
        blat, blon, balt = r["lat"], r["lon"], r["altitude_m"]
        if pd.isna(blat) or pd.isna(blon) or pd.isna(balt):
            continue
        if r["stale"]:
            skipped_stale += 1
            continue
        gws = r["gateways"]
        if gws is None or (isinstance(gws, float) and pd.isna(gws)):
            continue
        if not isinstance(gws, list):
            continue
        if not blat or not blon or not balt:
            continue
        for g in gws:
            gid = (g.get("gateway_id") or "").strip()
            if gid.lower() in PLACEHOLDER_IDS:
                skipped_placeholder += 1
                continue
            glat, glon = g.get("lat"), g.get("lon")
            # If the inline gateway data has no position, look it up
            if (glat is None or glon is None) and gw_db is not None and gid:
                hit = gw_db.get(gid.lower())
                if hit:
                    glat, glon = hit
            if glat is None or glon is None:
                skipped_no_pos += 1
                continue
            if abs(glat) < 0.001 and abs(glon) < 0.001:
                skipped_no_pos += 1
                continue
            dist = haversine_km(blat, blon, glat, glon)
            if dist > 2000:
                continue
            rows.append({
                "time": r["time"], "blat": blat, "blon": blon, "balt": balt,
                "gid": gid, "glat": glat, "glon": glon,
                "rssi": g.get("rssi") or r["rssi"],
                "snr": g.get("snr") or r["snr"],
                "sf": r.get("lora_sf") or 7,
                "dist_km": dist,
            })
    print(f"  skipped {skipped_stale} stale-GPS rows")
    print(f"  skipped {skipped_placeholder} placeholder gateway IDs")
    print(f"  skipped {skipped_no_pos} entries with no resolvable position")
    return pd.DataFrame(rows)


def plot(recs):
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    # 1) Distance histogram
    ax = axes[0, 0]
    ax.hist(recs["dist_km"], bins=30, color="#1a3a8f", edgecolor="white", alpha=0.85)
    ax.axvline(recs["dist_km"].median(), color="#d62a1a", linestyle="--",
               label=f"median {recs['dist_km'].median():.0f} km")
    ax.axvline(recs["dist_km"].max(), color="#2a9d4e", linestyle="--",
               label=f"max {recs['dist_km'].max():.0f} km")
    ax.set_xlabel("balloon ↔ gateway distance (km)")
    ax.set_ylabel("receptions")
    ax.set_title("Empirical reception-distance distribution")
    ax.legend()
    ax.grid(True, alpha=0.3)

    # 2) Distance vs altitude
    ax = axes[0, 1]
    sc = ax.scatter(recs["balt"] / 1000, recs["dist_km"],
                    c=recs["rssi"], cmap="viridis_r", s=18, alpha=0.85,
                    edgecolors="white", linewidths=0.3)
    # Geometric + 4/3-earth horizons
    alts = np.linspace(0, recs["balt"].max() / 1000 * 1.1, 200)
    horizon_geom = [math.sqrt(2 * EARTH_R_KM * h + h * h) for h in alts]
    horizon_43 = [math.sqrt(2 * K_REFRACT * EARTH_R_KM * h + h * h) for h in alts]
    ax.plot(alts, horizon_geom, "--", color="#666666", label="geometric horizon")
    ax.plot(alts, horizon_43, "-", color="#444444", label="4/3-Earth horizon")
    ax.axhline(link_budget_max_range_km(), color="#d62a1a", linestyle=":",
               label=f"link-budget max ({link_budget_max_range_km():.0f} km)")
    plt.colorbar(sc, ax=ax, label="RSSI (dBm)")
    ax.set_xlabel("balloon altitude (km)")
    ax.set_ylabel("distance to receiving gateway (km)")
    ax.set_title("Range vs altitude")
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(True, alpha=0.3)

    # 3) RSSI vs distance (link-budget validation)
    ax = axes[1, 0]
    ax.scatter(recs["dist_km"], recs["rssi"],
               c=recs["balt"] / 1000, cmap="plasma", s=18, alpha=0.85,
               edgecolors="white", linewidths=0.3)
    # Theoretical FSPL curve
    d_curve = np.linspace(10, recs["dist_km"].max() * 1.1, 200)
    rssi_curve = [TX_POWER_DBM + TX_GAIN_DBI + RX_GAIN_DBI - POL_LOSS_DB
                  - fspl_db(d) for d in d_curve]
    ax.plot(d_curve, rssi_curve, "--", color="#444444",
            label="theoretical FSPL\n(20 dBm + 1 dBi - 3 dB pol + 3 dBi)")
    sens = sx1262_sensitivity_dbm(sf=7)
    ax.axhline(sens, color="#d62a1a", linestyle=":",
               label=f"SF7 sensitivity ({sens:.0f} dBm)")
    ax.set_xlabel("distance (km)")
    ax.set_ylabel("RSSI at gateway (dBm)")
    ax.set_title("Measured RSSI vs FSPL model")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # 4) Theoretical context summary as text
    ax = axes[1, 1]
    ax.axis("off")
    max_alt = recs["balt"].max() / 1000
    max_d = recs["dist_km"].max()
    p95_d = recs["dist_km"].quantile(0.95)
    median_d = recs["dist_km"].median()
    horizon_4_3 = radio_horizon_km(recs["balt"].max())
    horizon_geom = math.sqrt(2 * EARTH_R_KM * max_alt + max_alt * max_alt)
    lb_max = link_budget_max_range_km()
    summary = f"""Empirical
─────────
n receptions analyzed: {len(recs)}
max altitude:          {max_alt:.2f} km
median range:          {median_d:.0f} km
p95 range:             {p95_d:.0f} km
**max range:           {max_d:.0f} km**

Theoretical at peak altitude ({max_alt:.1f} km)
─────────
geometric horizon:     {horizon_geom:.0f} km
4/3-Earth horizon:     {horizon_4_3:.0f} km
link-budget max (FSPL): {lb_max:.0f} km
SF7 sensitivity:       {sx1262_sensitivity_dbm():.0f} dBm

Reference records
─────────
TTN balloon record:    702 km (2019)
SODAQ @ 15 km alt:     354 km
our utilization:       {max_d / horizon_4_3 * 100:.0f}% of 4/3-horizon
                       {max_d / lb_max * 100:.0f}% of link-budget max
                       {max_d / 702 * 100:.0f}% of TTN record
"""
    ax.text(0.02, 0.98, summary, transform=ax.transAxes,
            family="monospace", fontsize=10, verticalalignment="top")

    plt.suptitle("Stratolink-3 transmission range — empirical vs theoretical",
                 fontsize=14, y=1.00)
    plt.tight_layout()
    plt.savefig(OUT_PNG, dpi=200, bbox_inches="tight")
    print(f"  wrote {OUT_PNG}")


def main():
    if not SBKEY:
        sys.exit("Set SBKEY env")
    print("Fetching telemetry...")
    df = fetch_all()
    print(f"  {len(df)} rows")
    print("Loading gateway position database...")
    gw_db = load_gateway_db()
    print(f"  {len(gw_db) if gw_db else 0} gateways with known position")

    print("Extracting (balloon, gateway) reception pairs...")
    recs = extract_receptions(df, gw_db)
    print(f"  {len(recs)} resolvable reception pairs")
    if len(recs) == 0:
        sys.exit("No resolvable receptions — check gateway lookup coverage")

    print(f"\nRange stats:")
    print(f"  median: {recs['dist_km'].median():.1f} km")
    print(f"  p95:    {recs['dist_km'].quantile(0.95):.1f} km")
    print(f"  max:    {recs['dist_km'].max():.1f} km")
    print(f"  max altitude: {recs['balt'].max():.0f} m")

    # Top-N longest receptions
    top = recs.nlargest(10, "dist_km")
    print("\nTop 10 longest receptions:")
    print(f"{'time':<25} {'gw':<25} {'dist':>6} {'alt':>6} {'rssi':>5} {'snr':>5}")
    for _, r in top.iterrows():
        print(f"{r['time'].isoformat()[:19]:<25} {r['gid'][:25]:<25} "
              f"{r['dist_km']:>5.0f}km {r['balt']:>5.0f}m {r['rssi']:>5} {r['snr']:>5}")

    plot(recs)


if __name__ == "__main__":
    main()
