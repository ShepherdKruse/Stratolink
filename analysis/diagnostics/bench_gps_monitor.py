"""Live GPS bench monitor — watches Supabase for a device and classifies each
new uplink FRESH / STALE / NOGPS / GARBAGE in real time. Built for the board-#2
GPS stale-fix reproduce/validate test (see firmware/GPS_TEST_PLAN.md).

Why this works while the board sits still: a *fresh* fix jitters cycle-to-cycle
(SIV count, speed ~0 noise, heading wander), so consecutive rows differ. A
*stale* fix re-reports the exact same (lat,lon,alt,sats,speed,heading) tuple —
that identity is the bug's signature, visible even stationary.

Usage:
    set -a; source ~/.config/stratolink/env; set +a
    python analysis/diagnostics/bench_gps_monitor.py            # device stratolink-2
    python analysis/diagnostics/bench_gps_monitor.py --device stratolink-2 --poll 15

Expected during the test:
    no foil  -> stream of FRESH (sats/speed wiggle)
    foil on, CURRENT firmware -> rows flip to STALE (frozen tuple)  = bug reproduced
    foil on, FIXED firmware   -> rows flip to NOGPS (lat null)      = fix confirmed
"""
from __future__ import annotations
import os, sys, time, argparse
import requests

SBURL = os.environ.get("SUPABASE_URL") or "https://iazmnyyfsobucndqncgw.supabase.co"
SBKEY = os.environ.get("SBKEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

C = {"FRESH": "\033[92m", "STALE": "\033[91m", "NOGPS": "\033[90m",
     "GARBAGE": "\033[95m", "0": "\033[0m", "B": "\033[1m"}


def classify(row, last_fresh):
    lat, lon, alt = row.get("lat"), row.get("lon"), row.get("altitude_m")
    sats, spd, hdg = row.get("gps_satellites"), row.get("gps_speed"), row.get("gps_heading")
    if lat is None:
        return "NOGPS", last_fresh
    if abs(lat) > 90 or (lon is not None and abs(lon) > 180):
        return "GARBAGE", last_fresh
    cur = (round(lat, 6), round(lon, 6),
           int(alt) if alt is not None else None,
           int(sats) if sats is not None else None,
           round(spd, 2) if spd is not None else None,
           round(hdg, 2) if hdg is not None else None)
    if last_fresh is not None and cur == last_fresh:
        return "STALE", last_fresh
    return "FRESH", cur


def fetch_recent(device, limit=60):
    url = f"{SBURL}/rest/v1/telemetry"
    params = {"device_id": f"eq.{device}",
              "select": "id,time,lat,lon,altitude_m,gps_satellites,gps_speed,"
                        "gps_heading,rssi,snr,battery_voltage,solar_voltage,pressure,temperature",
              "order": "time.asc", "limit": str(limit)}
    h = {"apikey": SBKEY, "Authorization": f"Bearer {SBKEY}"}
    r = requests.get(url, params=params, headers=h, timeout=20)
    r.raise_for_status()
    return r.json()


def fmt(row, cls):
    t = (row.get("time") or "")[11:19]
    lat, lon = row.get("lat"), row.get("lon")
    pos = f"{lat:9.5f},{lon:10.5f}" if lat is not None else "   --- NO FIX ---   "
    sats = row.get("gps_satellites"); spd = row.get("gps_speed")
    rssi = row.get("rssi"); bv = row.get("battery_voltage")
    col = C.get(cls, "")
    return (f"{t}  {col}{C['B']}{cls:<7}{C['0']} {pos}  "
            f"sats={int(sats) if sats is not None else 0:>2} spd={spd if spd is not None else 0:>5} "
            f"rssi={int(rssi) if rssi is not None else 0:>4} vbat={bv if bv is not None else 0:>5}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="stratolink-2")
    ap.add_argument("--poll", type=float, default=15.0, help="seconds between polls")
    a = ap.parse_args()
    if not SBKEY:
        sys.exit("Set SBKEY: set -a; source ~/.config/stratolink/env; set +a")

    print(f"Monitoring '{a.device}' on {SBURL}  (poll {a.poll}s, Ctrl-C to stop)\n")
    seen, last_fresh = set(), None
    tally = {"FRESH": 0, "STALE": 0, "NOGPS": 0, "GARBAGE": 0}
    # Prime state from history without spamming the screen
    try:
        for row in fetch_recent(a.device, limit=200):
            cls, last_fresh = classify(row, last_fresh)
            seen.add(row["id"]); tally[cls] += 1
        if sum(tally.values()):
            print(f"[history primed: {dict(tally)}]  waiting for new uplinks...\n")
        else:
            print("[no rows yet for this device — flash + power it and wait]\n")
    except Exception as e:
        print(f"warn: prime failed ({e})")

    while True:
        try:
            for row in fetch_recent(a.device):
                if row["id"] in seen:
                    continue
                cls, last_fresh = classify(row, last_fresh)
                seen.add(row["id"]); tally[cls] += 1
                run = f"  ({tally['FRESH']}F/{tally['STALE']}S/{tally['NOGPS']}N)"
                print(fmt(row, cls) + run)
        except Exception as e:
            print(f"warn: poll failed ({e})")
        time.sleep(a.poll)


if __name__ == "__main__":
    main()
