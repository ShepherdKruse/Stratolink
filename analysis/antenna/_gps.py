"""GPS fresh-fix classification for Stratolink-3 — the gate for all geometry.

WHY THIS EXISTS
---------------
Flight-3 had the u-blox stale-fix bug (firmware/GPS_BUG_BOARD2.md): when the
module stopped emitting fresh PVT messages, the SparkFun library kept returning
the *last cached* lat/lon/alt with fixOK still true.  The firmware transmitted
those frozen coordinates as if fresh.

For antenna geometry this is poison: when the reported position is stale, the
balloon's TRUE position is unknown (downwind of the frozen point), so every
distance / elevation / azimuth computed from the reported position is wrong.
The infamous "433 km, elevation -1.0deg (below horizon!)" reception is computed
against the May-17 freeze (lat 36.616, lon -121.572, alt 6924 m) — the
below-horizon angle is the tell that the position is fiction.

RULE: geometry uses FRESH fixes only.  (RSSI/SNR magnitudes are real even on a
stale fix — only the position is wrong — so RSSI-only stats may keep stale rows,
but anything angular/range-based must not.)

This mirrors classify() in analysis/diagnostics/gps_stale_audit.py, generalized
to run per-device (the audit only did the US stream; the EU leg is the bulk of
the reception data and must be classified too).

Classes per uplink:
  PRE_LAUNCH  before launch (ground testing)
  FRESH       valid fix, distinct tuple from the previous fresh fix
  STALE       valid-looking fix bit-identical to the previous fresh fix (the bug)
  NOGPS       firmware correctly reported no fix (null lat)
  GARBAGE     out-of-range coords (|lat|>90 etc.) from a pre-lock placeholder
"""
from __future__ import annotations

import pandas as pd
from datetime import datetime, timezone

# Launch: 2026-05-17 ~14:00 UTC from Dolores Park (firmware/GPS_BUG_BOARD2.md,
# STRATOLINK_3_FLIGHT_NOTES.md). Rows before this are bench/pre-launch.
LAUNCH_UTC = datetime(2026, 5, 17, 14, 0, 0, tzinfo=timezone.utc)

# The stale-fix tuple compares these fields; bit-identical => frozen cache.
_TUPLE_COLS = ("lat", "lon", "altitude_m", "gps_satellites", "gps_speed", "gps_heading")


def _fix_tuple(r) -> tuple:
    def rv(x, nd):
        return None if x is None or pd.isna(x) else round(float(x), nd)
    return (
        rv(r.get("lat"), 6), rv(r.get("lon"), 6),
        None if pd.isna(r.get("altitude_m")) else int(r["altitude_m"]),
        None if pd.isna(r.get("gps_satellites")) else int(r["gps_satellites"]),
        rv(r.get("gps_speed"), 2), rv(r.get("gps_heading"), 2),
    )


def classify_uplinks(df: pd.DataFrame) -> pd.DataFrame:
    """Add a 'gps_class' column to a per-uplink telemetry frame.

    df must have: time (tz-aware), device_id, lat, lon, altitude_m,
    gps_satellites, gps_speed, gps_heading.  Classification runs independently
    per device_id, in time order (each region stream is its own GPS history).
    """
    df = df.copy()
    df["gps_class"] = "?"
    df["consec_stale"] = 0

    for dev, idx in df.groupby("device_id").groups.items():
        sub = df.loc[idx].sort_values("time")
        last_fresh = None
        consec = 0
        for i, r in sub.iterrows():
            if r["time"] < LAUNCH_UTC:
                df.at[i, "gps_class"] = "PRE_LAUNCH"
                continue
            lat, lon = r.get("lat"), r.get("lon")
            if lat is not None and not pd.isna(lat) and (abs(lat) > 90 or abs(lon) > 180):
                df.at[i, "gps_class"] = "GARBAGE"
                continue
            if pd.isna(lat) or lat is None:
                df.at[i, "gps_class"] = "NOGPS"
                consec = 0
                continue
            cur = _fix_tuple(r)
            if last_fresh is not None and cur == last_fresh:
                consec += 1
                df.at[i, "gps_class"] = "STALE"
                df.at[i, "consec_stale"] = consec
            else:
                df.at[i, "gps_class"] = "FRESH"
                consec = 0
                last_fresh = cur
    return df


def summarize(df: pd.DataFrame) -> dict:
    """Quick class breakdown (post-launch) for the report."""
    flight = df[df["time"] >= LAUNCH_UTC]
    out = {"post_launch_uplinks": len(flight)}
    for dev in sorted(df["device_id"].unique()):
        sub = flight[flight["device_id"] == dev]
        out[dev] = sub["gps_class"].value_counts().to_dict()
    out["ALL"] = flight["gps_class"].value_counts().to_dict()
    return out
