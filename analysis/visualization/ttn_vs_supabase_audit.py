"""TTN storage vs Supabase audit.

Pulls all TTN uplinks since launch from the Storage Integration, decodes the
exact 35-byte v1 or 40-byte v2 payload, and diffs against Supabase rows. Surfaces:
  - Drops (TTN received → Supabase missing) — proves webhook issue
  - Differences in GPS sat / lat / lon / alt between firmware and DB
  - Whether the "frozen 32 sats" pattern is firmware-side or library-cache-side
"""
import os, base64, json, sys
from datetime import datetime, timezone, timedelta
from struct import unpack
from pathlib import Path
import requests

TTN_API_KEY = os.environ.get("TTN_API_KEY")
TTN_APP = "stratolink"
TTN_CLUSTER = "https://nam1.cloud.thethings.network"

SBKEY = os.environ.get("SBKEY")
SBURL = "https://iazmnyyfsobucndqncgw.supabase.co"

if not TTN_API_KEY:
    sys.exit("Set TTN_API_KEY env")
if not SBKEY:
    sys.exit("Set SBKEY env")


def fetch_ttn_uplinks(since: datetime) -> list[dict]:
    """Pull all uplinks since `since` from TTN storage integration."""
    url = f"{TTN_CLUSTER}/api/v3/as/applications/{TTN_APP}/packages/storage/uplink_message"
    params = {
        "after": since.isoformat().replace("+00:00", "Z"),
        "order": "received_at",
        "limit": "1000",
    }
    # TTN returns ndjson (one JSON object per line)
    headers = {
        "Authorization": f"Bearer {TTN_API_KEY}",
        "Accept": "text/event-stream",
    }
    r = requests.get(url, params=params, headers=headers, timeout=60)
    r.raise_for_status()
    rows = []
    for line in r.text.splitlines():
        line = line.strip()
        if not line:
            continue
        # Storage integration can return either {"result": {...}} per line OR plain {...}
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "result" in d:
            d = d["result"]
        rows.append(d)
    return rows


def decode_payload(b64: str) -> dict | None:
    """Decode an exact-length v1/v2 big-endian telemetry payload."""
    try:
        b = base64.b64decode(b64)
    except Exception:
        return None
    if len(b) not in (35, 40):
        return None
    decoded = {
        "lat":           unpack(">i", b[0:4])[0] / 1e7,
        "lon":           unpack(">i", b[4:8])[0] / 1e7,
        "altitude_m":    unpack(">i", b[8:12])[0],
        "temperature":   unpack(">h", b[12:14])[0] / 10.0,
        "pressure":      unpack(">H", b[14:16])[0] / 10.0,
        "solar_mv":      unpack(">H", b[16:18])[0],
        "vstor_mv":      unpack(">H", b[18:20])[0],
        "gps_speed":     unpack(">H", b[20:22])[0] / 100.0,
        "gps_heading":   unpack(">H", b[22:24])[0] / 100.0,
        "gps_sats":      b[24],
        "accel_x":       unpack(">h", b[25:27])[0] / 100.0,
        "accel_y":       unpack(">h", b[27:29])[0] / 100.0,
        "accel_z":       unpack(">h", b[29:31])[0] / 100.0,
        "uv_index":      b[31],
        "ambient_lux":   unpack(">H", b[32:34])[0],
        "acoustic":      b[34] & 0x01 if len(b) == 40 else b[34],
    }
    if len(b) == 40:
        decoded.update({
            "wire_version":       2,
            "power_tier":         (b[34] >> 1) & 0x07,
            "reset_cause":        (b[34] >> 4) & 0x07,
            "command_ack_valid":  bool(b[34] & 0x80),
            "boot_count":         b[35],
            "fix_age_min":        unpack(">H", b[36:38])[0],
            "last_command_seq":   b[38],
            "relay_enabled":      bool(b[39] & 0x80),
            "relay_fwd_delta":    (b[39] >> 4) & 0x07,
            "ctt_tags_delta":     b[39] & 0x0F,
        })
    else:
        decoded["wire_version"] = 1
    return decoded


def fetch_supabase_rows(since: datetime) -> list[dict]:
    url = f"{SBURL}/rest/v1/telemetry"
    params = {
        "device_id": "eq.stratolink-3",
        "select": "time,lat,lon,altitude_m,gps_satellites,gps_speed,gps_heading,pressure,temperature,rssi",
        "order": "time.asc",
        "time": f"gte.{since.isoformat().replace('+00:00', 'Z')}",
        "limit": "5000",
    }
    h = {"apikey": SBKEY, "Authorization": f"Bearer {SBKEY}"}
    r = requests.get(url, params=params, headers=h, timeout=30)
    r.raise_for_status()
    return r.json()


def main():
    since = datetime.now(timezone.utc) - timedelta(days=3)
    print(f"Audit since {since.isoformat()} UTC")

    print("\n[1/3] Fetching TTN storage history...")
    ttn = fetch_ttn_uplinks(since)
    print(f"  TTN uplinks: {len(ttn)}")

    print("\n[2/3] Fetching Supabase rows...")
    supa = fetch_supabase_rows(since)
    print(f"  Supabase rows: {len(supa)}")

    # Build a quick index of supabase rows by received_at second
    supa_by_minute = {}
    for r in supa:
        t = datetime.fromisoformat(r["time"].replace("Z", "+00:00"))
        # match by minute granularity
        key = t.replace(second=0, microsecond=0)
        supa_by_minute.setdefault(key, []).append(r)

    # Walk TTN rows, decode, diff
    print("\n[3/3] Comparing TTN vs Supabase...\n")
    drops = []
    decoded_rows = []
    print(f"{'time':<25} {'devid':<20} {'fcnt':>5} {'sats':>4} {'lat':>10} {'lon':>11} {'alt':>5} {'P':>6} {'T':>5} {'sup?':>5}")
    for u in ttn:
        ts = u.get("received_at") or u.get("uplink_message", {}).get("received_at")
        if not ts:
            continue
        t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        ed = u.get("end_device_ids", {})
        devid = ed.get("device_id", "?")
        um = u.get("uplink_message", {})
        fcnt = um.get("f_cnt", "?")
        b64 = um.get("frm_payload", "")
        dec = decode_payload(b64)

        match_key = t.replace(second=0, microsecond=0)
        matched = None
        for offset_min in (0, -1, 1, -2, 2):
            k = match_key + timedelta(minutes=offset_min)
            if k in supa_by_minute:
                matched = supa_by_minute[k][0]
                break
        in_supa = "yes" if matched else "DROP"
        if not matched:
            drops.append((ts, fcnt, devid))

        if dec:
            decoded_rows.append({"t": t, "fcnt": fcnt, "devid": devid, **dec, "in_supa": bool(matched)})
            print(f"{ts[:19]:<25} {devid:<20} {fcnt:>5} {dec['gps_sats']:>4} "
                  f"{dec['lat']:>10.4f} {dec['lon']:>11.4f} {dec['altitude_m']:>5} "
                  f"{dec['pressure']:>6.1f} {dec['temperature']:>5.1f} {in_supa:>5}")
        else:
            print(f"{ts[:19]:<25} {devid:<20} {fcnt:>5} {'?':>4} {'?':>10} {'?':>11} {'?':>5} "
                  f"{'?':>6} {'?':>5} {in_supa:>5}")

    print(f"\n=== summary ===")
    print(f"TTN uplinks total:    {len(ttn)}")
    print(f"Decoded successfully: {len(decoded_rows)}")
    print(f"Drops (TTN→no DB):    {len(drops)}")
    if drops:
        print("  drops:")
        for ts, fcnt, did in drops[:20]:
            print(f"    {ts} fcnt={fcnt} dev={did}")

    # Now diagnostic: look at how lat/lon/sats changes between TTN uplinks
    print("\n=== firmware-side GPS pattern (decoded from TTN payload, no webhook involvement) ===")
    print(f"{'time':<25} {'fcnt':>5} {'sats':>4} {'lat':>10} {'lon':>11} {'alt':>5}  pattern")
    prev = None
    for d in decoded_rows[-40:]:
        flag = ""
        if prev:
            same = (d["lat"] == prev["lat"] and d["lon"] == prev["lon"]
                    and d["altitude_m"] == prev["altitude_m"])
            if same and d["lat"] != 0:
                flag = "← STALE (identical to prior fix)"
            elif d["lat"] == 0 and d["lon"] == 0:
                flag = "(NOGPS)"
        print(f"{d['t'].isoformat()[:19]:<25} {d['fcnt']:>5} {d['gps_sats']:>4} "
              f"{d['lat']:>10.4f} {d['lon']:>11.4f} {d['altitude_m']:>5}  {flag}")
        prev = d


if __name__ == "__main__":
    main()
