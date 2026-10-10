#!/usr/bin/env python3
"""Gateway census for Stratolink-3, "every gateway that heard us, and how TTN
actually performed."  Foundation for the network-choice study (TTN vs Helium vs
Meshtastic).

Pulls flight telemetry for the two flight-3 device IDs (excludes the
`stratolink-2` bench board, which is on the same table but is a strong-signal
bench unit), explodes the per-uplink `gateways[]` JSONB into one row per
(uplink x receiving gateway), classifies GPS freshness (geometry needs fresh
fixes), then characterizes:

  * the named-vs-Packet-Broker split (what we can and cannot see about who
    heard us, the roaming/anonymization story that bears directly on Helium)
  * a per-gateway census: receptions, distinct uplinks heard, RSSI/SNR, coords
  * region (US915/EU868) and SF breakdowns

Run:
  set -a; source ~/.config/stratolink/env; set +a
  analysis/.venv/bin/python analysis/network/10_gateway_census.py

Outputs:
  analysis/network/data/receptions.parquet / .csv   (exploded, fresh/stale tagged)
  analysis/network/data/gateway_census.csv          (one row per gateway_id)
  prints a NUMERIC SUMMARY block (quote verbatim, do not pre-write numbers).
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pandas as pd
import requests

# Reuse the antenna study's vetted helpers (geometry, creds, GPS classifier).
HERE = pathlib.Path(__file__).resolve().parent
ANT = HERE.parent / "antenna"
sys.path.insert(0, str(ANT))
from _common import (  # noqa: E402
    DEVICE_IDS, REGION_BY_DEVICE, get_creds, rest_headers, is_anonymized,
    haversine_km, slant_range_km, elevation_angle_deg, depression_angle_deg,
)
from _gps import classify_uplinks, LAUNCH_UTC  # noqa: E402

DATA = HERE / "data"
DATA.mkdir(exist_ok=True)
PAGE = 1000


def fetch_device(tele, headers, device_id):
    out, offset = [], 0
    while True:
        h = dict(headers)
        h["Range-Unit"] = "items"
        h["Range"] = f"{offset}-{offset + PAGE - 1}"
        params = {"select": "*", "device_id": f"eq.{device_id}", "order": "time.asc"}
        r = requests.get(tele, headers=h, params=params, timeout=120)
        r.raise_for_status()
        batch = r.json()
        out.extend(batch)
        if len(batch) < PAGE:
            break
        offset += PAGE
    return out


def as_list(v):
    if isinstance(v, list):
        return v
    if isinstance(v, str) and v:
        try:
            return json.loads(v)
        except Exception:
            return []
    return []


def q(s, p):
    s = pd.to_numeric(s, errors="coerce").dropna()
    return float(np.percentile(s, p)) if len(s) else float("nan")


def main() -> int:
    base, key = get_creds()
    headers = rest_headers(key)
    tele = f"{base}/rest/v1/telemetry"

    frames = []
    for dev in DEVICE_IDS:  # ["stratolink-3", "stratolink-3-eu"], excludes stratolink-2
        rows = fetch_device(tele, headers, dev)
        print(f"fetched {dev}: {len(rows)} uplinks")
        if rows:
            df = pd.DataFrame(rows)
            df["region"] = REGION_BY_DEVICE.get(dev, "?")
            frames.append(df)
    up = pd.concat(frames, ignore_index=True)
    up["time"] = pd.to_datetime(up["time"], utc=True, errors="coerce")
    up = up.sort_values("time").reset_index(drop=True)

    # GPS freshness (per device stream), geometry uses FRESH only.
    up = classify_uplinks(up)
    post = up[up["time"] >= LAUNCH_UTC]
    print(f"\nuplinks total={len(up)}  post-launch={len(post)}")
    print("gps_class (post-launch):",
          dict(post["gps_class"].value_counts()))

    # ---- explode gateways[] -> receptions ---------------------------------
    recs = []
    n_with_array = 0
    for _, row in up.iterrows():
        gws = as_list(row.get("gateways"))
        base_rec = dict(
            time=row.get("time"), device_id=row.get("device_id"),
            region=row.get("region"), gps_class=row.get("gps_class"),
            balloon_lat=row.get("lat"), balloon_lon=row.get("lon"),
            balloon_alt=row.get("altitude_m"),
            spreading_factor=row.get("lora_sf"), frequency_hz=row.get("frequency_hz"),
        )
        if gws:
            n_with_array += 1
            for g in gws:
                gid = g.get("gateway_id")
                recs.append({**base_rec, "gateway_id": gid,
                             "gateway_lat": g.get("lat"), "gateway_lon": g.get("lon"),
                             "gateway_alt": g.get("alt"),
                             "rssi": g.get("rssi"), "snr": g.get("snr"),
                             "anonymized": is_anonymized(gid)})
        elif pd.notna(row.get("rssi")):
            # uplink with top-level rssi but no gateways[] array
            recs.append({**base_rec, "gateway_id": None,
                         "gateway_lat": np.nan, "gateway_lon": np.nan,
                         "gateway_alt": np.nan,
                         "rssi": row.get("rssi"), "snr": row.get("snr"),
                         "anonymized": True})
    r = pd.DataFrame(recs)
    for c in ("balloon_lat", "balloon_lon", "balloon_alt", "gateway_lat",
              "gateway_lon", "gateway_alt", "rssi", "snr", "frequency_hz"):
        r[c] = pd.to_numeric(r[c], errors="coerce")
    r["spreading_factor"] = pd.to_numeric(r["spreading_factor"], errors="coerce").astype("Int64")

    # geometry (only where the gateway carries coords AND the balloon fix is FRESH)
    def geom(x):
        if (pd.isna(x.gateway_lat) or pd.isna(x.gateway_lon)
                or pd.isna(x.balloon_lat) or pd.isna(x.balloon_lon)):
            return pd.Series([np.nan, np.nan, np.nan, np.nan])
        gc = haversine_km(x.balloon_lat, x.balloon_lon, x.gateway_lat, x.gateway_lon)
        ab = float(x.balloon_alt) if not pd.isna(x.balloon_alt) else 0.0
        ag = float(x.gateway_alt) if not pd.isna(x.gateway_alt) else 0.0
        return pd.Series([gc, slant_range_km(gc, ab, ag),
                          elevation_angle_deg(gc, ab, ag),
                          depression_angle_deg(gc, ab, ag)])
    r[["gc_km", "slant_km", "elev_gw_deg", "depr_balloon_deg"]] = r.apply(geom, axis=1)
    r["fresh"] = r["gps_class"] == "FRESH"
    # TRUE RF band from the uplink frequency (device_id is NOT a reliable band
    # tag, the webhook collapses late EU868 uplinks onto the `stratolink-3`
    # US app id, commit 0e1a39a). 868.x MHz = EU868, 90x MHz = US915.
    f_mhz = pd.to_numeric(r["frequency_hz"], errors="coerce") / 1e6
    r["band"] = np.where(f_mhz < 900, "EU868", "US915")
    r.loc[f_mhz.isna(), "band"] = "unknown"
    r["is_prelaunch"] = r["gps_class"] == "PRE_LAUNCH"
    r = r.sort_values("time").reset_index(drop=True)

    r.to_parquet(DATA / "receptions.parquet", index=False)
    r.to_csv(DATA / "receptions.csv", index=False)

    # ---- the named-vs-anonymized split ------------------------------------
    n_recs = len(r)
    n_anon = int(r["anonymized"].sum())
    n_named = n_recs - n_anon
    named = r[~r["anonymized"]]
    anon = r[r["anonymized"]]
    n_named_gw = named["gateway_id"].nunique()
    # how many DISTINCT uplinks were heard by at least one named gateway?
    up_keys = ["time", "device_id"]
    up_heard = r.dropna(subset=["rssi"]).drop_duplicates(up_keys)
    up_named = named.drop_duplicates(up_keys)
    up_anon_only = up_heard.merge(up_named[up_keys], on=up_keys, how="left", indicator=True)
    up_anon_only = int((up_anon_only["_merge"] == "left_only").sum())

    print("\n==== NAMED vs PACKET-BROKER (anonymized) ====")
    print(f"receptions total={n_recs}  named={n_named}  anonymized={n_anon} "
          f"({100*n_anon/max(1,n_recs):.1f}% anon)")
    print(f"distinct NAMED gateways: {n_named_gw}")
    print(f"uplinks heard (any gw): {len(up_heard)}  "
          f"heard by >=1 named gw: {len(up_named)}  "
          f"heard ONLY by anonymized/packetbroker: {up_anon_only}")

    # coords provenance
    geo = r[r["gc_km"].notna()]
    print(f"\ncoord-carrying receptions: {len(geo)} "
          f"(named={int((~geo['anonymized']).sum())}, anon={int(geo['anonymized'].sum())})")
    print("anonymized gateway_id values seen:",
          dict(anon["gateway_id"].fillna("<null>").value_counts()))

    # ---- per-gateway census (named) ---------------------------------------
    def agg(g):
        return pd.Series({
            "receptions": len(g),
            "uplinks_heard": g.drop_duplicates(up_keys).shape[0],
            "region": "/".join(sorted(g["region"].dropna().unique())),
            "rssi_med": q(g["rssi"], 50), "rssi_best": q(g["rssi"], 100),
            "snr_med": q(g["snr"], 50), "snr_best": q(g["snr"], 100),
            "has_coords": int(g["gateway_lat"].notna().any()),
            "gw_lat": g["gateway_lat"].dropna().median(),
            "gw_lon": g["gateway_lon"].dropna().median(),
            "gc_max_km": q(g["gc_km"], 100),
        })
    census = (named.groupby("gateway_id").apply(agg, include_groups=False)
              .sort_values("receptions", ascending=False))
    census.to_csv(DATA / "gateway_census.csv")

    # Geolocate gateways: prefer self-reported coords from gateways[]; fall back
    # to the cached public TTN gateway registry (~63k gateways) by exact id.
    import os
    reg_path = os.path.expanduser("~/.cache/stratolink/ttn_gateways.csv")
    if os.path.exists(reg_path):
        reg = pd.read_csv(reg_path)
        m = census.reset_index().merge(reg, left_on="gateway_id", right_on="id", how="left")
        m["final_lat"] = m["gw_lat"].where(m["gw_lat"].notna(), m["lat"])
        m["final_lon"] = m["gw_lon"].where(m["gw_lon"].notna(), m["lon"])
        m.to_csv(DATA / "gateway_census_located.csv", index=False)
        nloc = int(m["final_lat"].notna().sum())
        print(f"geolocated {nloc}/{len(census)} named gateways "
              f"(covers {int(m.loc[m['final_lat'].notna(),'receptions'].sum())} receptions)")

    print(f"\n==== NAMED GATEWAY CENSUS (top 30 of {len(census)}) ====")
    with pd.option_context("display.max_rows", 40, "display.width", 200,
                           "display.float_format", lambda v: f"{v:.1f}"):
        print(census.head(30).to_string())

    # ---- signal stats (all receptions; RSSI/SNR are real even on stale fix)
    print("\n==== SIGNAL by REGION (all receptions) ====")
    for reg in ("US", "EU", "ALL"):
        s = r if reg == "ALL" else r[r["region"] == reg]
        print(f"{reg:>3}: n={len(s):4d}  RSSI med={q(s['rssi'],50):6.1f} "
              f"min={q(s['rssi'],0):6.1f} max={q(s['rssi'],100):6.1f}  | "
              f"SNR med={q(s['snr'],50):5.1f} min={q(s['snr'],0):5.1f}")

    print("\n==== SF distribution ====")
    print("receptions:", dict(r["spreading_factor"].value_counts(dropna=True).sort_index()))
    print("uplinks   :", dict(post.drop_duplicates(["time","device_id"])["lora_sf"]
                              .value_counts(dropna=True).sort_index()))

    # ---- redundancy: how many gateways heard each uplink ------------------
    gw_per_up = r.dropna(subset=["rssi"]).groupby(up_keys).size()
    print("\n==== GATEWAY DIVERSITY per uplink ====")
    print(f"gateways/uplink: mean={gw_per_up.mean():.2f} median={gw_per_up.median():.0f} "
          f"max={gw_per_up.max()}  (1-gw uplinks: {int((gw_per_up==1).sum())}/"
          f"{len(gw_per_up)} = {100*(gw_per_up==1).mean():.0f}%)")

    print("\nwrote", DATA / "receptions.csv", "and", DATA / "gateway_census.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
