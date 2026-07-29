#!/usr/bin/env python3
"""Build the per-reception table: one row per (uplink x receiving gateway).

Explodes the `gateways` JSONB array so we keep EVERY gateway that heard each
uplink (with that gateway's own rssi/snr), not just the top-level best. Attaches
balloon lat/lon/alt + the uplink settings (lora_sf, frequency_hz), then computes
geometry for receptions whose gateway carries coordinates (the "packetbroker"
entries; named gateways have null coords).

Run (no creds needed; reads cached parquet):
  analysis/.venv/bin/python analysis/antenna/20_receptions.py

Outputs: analysis/antenna/data/receptions.parquet / .csv
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

from _common import (
    DATA, REGION_BY_DEVICE, haversine_km, slant_range_km,
    elevation_angle_deg, depression_angle_deg, is_anonymized,
)


def load_raw() -> pd.DataFrame:
    pq, csv = DATA / "telemetry_raw.parquet", DATA / "telemetry_raw.csv"
    if pq.exists():
        df = pd.read_parquet(pq)
    elif csv.exists():
        df = pd.read_csv(csv)
    else:
        sys.stderr.write("No cached telemetry. Run 10_fetch.py first.\n")
        sys.exit(2)
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
    return df


def as_list(v):
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


def main() -> int:
    df = load_raw()
    n_uplinks = len(df)

    recs = []
    have_array = 0
    for _, row in df.iterrows():
        region = row.get("region") or REGION_BY_DEVICE.get(row.get("device_id"), "?")
        b_lat, b_lon, b_alt = row.get("lat"), row.get("lon"), row.get("altitude_m")
        sf = row.get("lora_sf")
        freq = row.get("frequency_hz")
        gws = as_list(row.get("gateways"))
        base = dict(
            time=row.get("time"), device_id=row.get("device_id"), region=region,
            balloon_lat=b_lat, balloon_lon=b_lon, balloon_alt=b_alt,
            spreading_factor=sf, frequency_hz=freq,
        )
        if gws:
            have_array += 1
            for g in gws:
                gid = g.get("gateway_id")
                recs.append({
                    **base,
                    "gateway_id": gid,
                    "gateway_lat": g.get("lat"),
                    "gateway_lon": g.get("lon"),
                    "gateway_alt": g.get("alt"),
                    "rssi": g.get("rssi"),
                    "snr": g.get("snr"),
                    "anonymized": is_anonymized(gid),
                })
        else:
            # uplink with TTN metadata but no gateways[] array: keep the
            # top-level rssi/snr as a single best-gateway reception.
            recs.append({
                **base,
                "gateway_id": None, "gateway_lat": np.nan, "gateway_lon": np.nan,
                "gateway_alt": np.nan, "rssi": row.get("rssi"), "snr": row.get("snr"),
                "anonymized": True,
            })

    r = pd.DataFrame(recs)
    print(f"PER-GATEWAY mode: {have_array}/{n_uplinks} uplinks carried a gateways[] array.")

    for c in ("balloon_lat", "balloon_lon", "balloon_alt", "gateway_lat",
              "gateway_lon", "gateway_alt", "rssi", "snr", "frequency_hz"):
        r[c] = pd.to_numeric(r[c], errors="coerce")
    r["spreading_factor"] = pd.to_numeric(r["spreading_factor"], errors="coerce").astype("Int64")

    def geom(x):
        if (pd.isna(x.gateway_lat) or pd.isna(x.gateway_lon)
                or pd.isna(x.balloon_lat) or pd.isna(x.balloon_lon)):
            return pd.Series([np.nan, np.nan, np.nan, np.nan])
        gc = haversine_km(x.balloon_lat, x.balloon_lon, x.gateway_lat, x.gateway_lon)
        alt_b = float(x.balloon_alt) if not pd.isna(x.balloon_alt) else 0.0
        alt_g = float(x.gateway_alt) if not pd.isna(x.gateway_alt) else 0.0
        return pd.Series([
            gc, slant_range_km(gc, alt_b, alt_g),
            elevation_angle_deg(gc, alt_b, alt_g),
            depression_angle_deg(gc, alt_b, alt_g),
        ])

    r[["gc_km", "slant_km", "elev_gw_deg", "depr_balloon_deg"]] = r.apply(geom, axis=1)
    r = r.sort_values("time").reset_index(drop=True)

    pq, csv = DATA / "receptions.parquet", DATA / "receptions.csv"
    try:
        r.to_parquet(pq, index=False)
        print(f"wrote {pq}")
    except Exception as e:  # pragma: no cover
        print(f"parquet failed ({e})")
    r.to_csv(csv, index=False)
    print(f"wrote {csv}")

    print(f"\nreceptions: {len(r)} rows from {n_uplinks} uplinks")
    print(f"with usable gateway coords (geometry computed): {int(r['gc_km'].notna().sum())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
