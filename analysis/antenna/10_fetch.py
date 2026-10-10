#!/usr/bin/env python3
"""Pull ALL flight telemetry for both flight-3 device IDs; cache to parquet+csv.

Run:
  set -a; source ~/.config/stratolink/env; set +a
  analysis/.venv/bin/python analysis/antenna/10_fetch.py

Outputs:
  analysis/antenna/data/telemetry_raw.parquet   (gateways kept as JSON string)
  analysis/antenna/data/telemetry_raw.csv
"""
from __future__ import annotations

import json
import sys

import pandas as pd
import requests

from _common import DATA, DEVICE_IDS, REGION_BY_DEVICE, get_creds, rest_headers

PAGE = 1000


def fetch_device(tele, headers, device_id) -> list[dict]:
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


def main() -> int:
    base, key = get_creds()
    headers = rest_headers(key)
    tele = f"{base}/rest/v1/telemetry"

    frames = []
    for dev in DEVICE_IDS:
        rows = fetch_device(tele, headers, dev)
        print(f"{dev}: {len(rows)} rows")
        if rows:
            df = pd.DataFrame(rows)
            df["region"] = REGION_BY_DEVICE.get(dev, "?")
            frames.append(df)
    if not frames:
        print("No rows fetched.")
        return 1

    df = pd.concat(frames, ignore_index=True)
    for col in ("time", "created_at"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")
    df = df.sort_values("time").reset_index(drop=True)
    print(f"combined: {len(df)} rows")
    print(f"time span: {df['time'].min()} -> {df['time'].max()} (UTC)")

    df_out = df.copy()
    if "gateways" in df_out.columns:
        df_out["gateways"] = df_out["gateways"].apply(
            lambda v: json.dumps(v) if not isinstance(v, (str, type(None))) else v
        )

    pq, csv = DATA / "telemetry_raw.parquet", DATA / "telemetry_raw.csv"
    try:
        df_out.to_parquet(pq, index=False)
        print(f"wrote {pq}")
    except Exception as e:  # pragma: no cover
        print(f"parquet failed ({e}); csv only")
    df_out.to_csv(csv, index=False)
    print(f"wrote {csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
