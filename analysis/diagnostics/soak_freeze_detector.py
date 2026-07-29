"""Historical GPS repeated-tuple triage for Supabase telemetry.

Repeated rounded position tuples can flag the flight-3 frozen-location symptom,
but they cannot prove stale GNSS data: a stationary receiver can legitimately
quantize to the same values. Current telemetry does not expose GNSS iTOW or fix
age. Treat this only as a suspect-run screen; use the firmware's iTOW freshness
gate and hardware sky HIL for actual stale-fix qualification.

Usage:
    set -a; source ~/.config/stratolink/env; set +a
    python analysis/diagnostics/soak_freeze_detector.py --device stratolink-2 --since 2026-06-01T00:00:00
    # default --since = 6h ago is not available offline; pass it explicitly.

Verdict: SUSPECT if any REPEAT run reaches --min-cycles (default 4).
"""
from __future__ import annotations
import os, sys, argparse

SBURL = os.environ.get("SUPABASE_URL") or "https://iazmnyyfsobucndqncgw.supabase.co"
SBKEY = os.environ.get("SBKEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")


def fetch(device, since):
    import requests

    rows, off = [], 0
    h = {"apikey": SBKEY, "Authorization": f"Bearer {SBKEY}"}
    while True:
        params = {"device_id": f"eq.{device}", "time": f"gte.{since}",
                  "select": "time,lat,lon,altitude_m,gps_satellites,gps_speed,gps_heading,rssi,battery_voltage,temperature",
                  "order": "time.asc", "limit": 1000, "offset": off}
        r = requests.get(f"{SBURL}/rest/v1/telemetry", params=params, headers=h, timeout=30)
        r.raise_for_status()
        b = r.json(); rows += b
        if len(b) < 1000:
            break
        off += 1000
    return rows


def classify(rows):
    last = None
    out = []
    for r in rows:
        lat, lon, alt = r.get("lat"), r.get("lon"), r.get("altitude_m")
        sats, spd, hdg = r.get("gps_satellites"), r.get("gps_speed"), r.get("gps_heading")
        if lat is None:
            cls = "NOGPS"
        elif abs(lat) > 90 or (lon is not None and abs(lon) > 180):
            cls = "GARBAGE"
        else:
            cur = (round(lat, 6), round(lon, 6), int(alt) if alt is not None else None,
                   int(sats) if sats is not None else None,
                   round(spd, 2) if spd is not None else None,
                   round(hdg, 2) if hdg is not None else None)
            cls = "REPEAT" if (last is not None and cur == last) else "CHANGED"
            if cls == "CHANGED":
                last = cur
        out.append((r, cls))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="stratolink-2")
    ap.add_argument("--since", required=True, help="ISO8601 UTC, e.g. 2026-06-01T00:00:00")
    ap.add_argument("--min-cycles", type=int, default=4)
    a = ap.parse_args()
    if not SBKEY:
        sys.exit("Set SBKEY: set -a; source ~/.config/stratolink/env; set +a")

    rows = fetch(a.device, a.since)
    if not rows:
        print(f"No {a.device} rows since {a.since} yet."); return
    cl = classify(rows)
    from collections import Counter
    counts = Counter(c for _, c in cl)
    t0, t1 = rows[0]["time"][:19], rows[-1]["time"][:19]
    print(f"{a.device}: {len(rows)} uplinks  {t0} -> {t1}")
    print(
        f"  CHANGED={counts.get('CHANGED',0)}  "
        f"REPEAT={counts.get('REPEAT',0)}  "
        f"NOGPS={counts.get('NOGPS',0)}  "
        f"GARBAGE={counts.get('GARBAGE',0)}"
    )

    # Longest suspect repeated-tuple run.
    best = (0, None, None, None); i = 0
    while i < len(cl):
        if cl[i][1] == "REPEAT":
            j = i
            while j < len(cl) and cl[j][1] == "REPEAT":
                j += 1
            n = j - i
            # The repeated tuple is anchored by the last changed row.
            frozen = next(
                (
                    cl[k][0]
                    for k in range(i - 1, -1, -1)
                    if cl[k][1] == "CHANGED"
                ),
                cl[i][0],
            )
            dur_min = (_ts(cl[j-1][0]["time"]) - _ts(cl[i][0]["time"])) / 60.0
            if n > best[0]:
                best = (n, cl[i][0]["time"][:19], dur_min, frozen)
            i = j
        else:
            i += 1

    if best[0] >= a.min_cycles:
        f = best[3]
        print(f"\n  *** SUSPECT REPEATED GPS TUPLE *** longest run = {best[0]} uplinks "
              f"({best[2]:.0f} min) starting {best[1]}")
        print(
            f"      lat={f.get('lat')} lon={f.get('lon')} "
            f"sats={f.get('gps_satellites')} — not proof without iTOW/fix age"
        )
    elif best[0] > 0:
        print(
            f"\n  longest repeat run: {best[0]} uplinks "
            f"({best[2]:.0f} min) at {best[1]} — below suspect threshold"
        )
    else:
        print(
            "\n  no repeated tuples; this still does not independently prove "
            "GNSS freshness"
        )


def _ts(s):
    # parse 'YYYY-MM-DDTHH:MM:SS...' to epoch seconds (naive, UTC)
    import datetime
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


if __name__ == "__main__":
    main()
