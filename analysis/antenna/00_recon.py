"""Stratolink telemetry recon — discover schema, counts, and signal-data availability.

Writes a durable markdown report to analysis/antenna/_recon.md so findings survive
context clearing. Source creds first:
    set -a; source ~/.config/stratolink/env; set +a
"""
import os, json, urllib.request, urllib.parse, collections, datetime

URL = os.environ.get("SUPABASE_URL") or os.environ.get("SBURL")
KEY = os.environ.get("SBKEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
OUT = os.path.join(os.path.dirname(__file__), "_recon.md")

lines = []
def p(*a):
    s = " ".join(str(x) for x in a)
    lines.append(s)

def get(path):
    req = urllib.request.Request(
        URL + "/rest/v1/" + path,
        headers={"apikey": KEY, "Authorization": "Bearer " + KEY, "Prefer": "count=exact"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r), r.headers.get("Content-Range")

p("# Stratolink telemetry recon")
p(f"_generated {datetime.datetime.utcnow().isoformat()}Z_\n")
p(f"- URL host: `{URL.split('//')[-1].split('.')[0] if URL else None}`")
p(f"- creds present: URL={bool(URL)} KEY={bool(KEY)}\n")

try:
    rows, cr = get("telemetry?select=*&limit=1")
    p("## telemetry table")
    p(f"- total rows (Content-Range): `{cr}`")
    if rows:
        cols = sorted(rows[0].keys())
        p(f"- columns ({len(cols)}):")
        for c in cols:
            v = rows[0][c]
            vs = json.dumps(v)[:80] if v is not None else "null"
            p(f"    - `{c}` = {vs}")
    # device id breakdown
    allrows, _ = get("telemetry?select=device_id&limit=20000")
    c = collections.Counter(x.get("device_id") for x in allrows)
    p("\n- device_id counts:")
    for k, v in c.most_common():
        p(f"    - `{k}`: {v}")

    # signal columns non-null counts — try common names
    sigcols = ["rssi", "snr", "spreading_factor", "sf", "data_rate", "frequency",
               "gateway_id", "gateway", "gateways", "gateway_lat", "gateway_lon",
               "rx_metadata", "raw", "metadata", "consumed_airtime", "bandwidth",
               "lat", "lon", "latitude", "longitude", "altitude_m", "altitude",
               "pressure", "battery_voltage", "received_at", "created_at", "time",
               "tx_count", "fix_age", "region", "band", "hdop"]
    present = [c for c in (cols if rows else []) if c in sigcols]
    p("\n- signal/RF-relevant columns present:", ", ".join(f"`{c}`" for c in present) or "(none of the guessed names)")

    # Pull a few full sample rows for the strongest-signal inspection
    p("\n## sample rows (first 3, all columns)")
    samp, _ = get("telemetry?select=*&order=" + urllib.parse.quote("received_at.asc" if rows and "received_at" in rows[0] else "id.asc") + "&limit=3")
    for i, r in enumerate(samp):
        p(f"\n### row {i}")
        p("```json")
        p(json.dumps(r, indent=2, default=str)[:2500])
        p("```")

except Exception as e:
    import traceback
    p("ERROR:", type(e).__name__, str(e))
    p("```")
    p(traceback.format_exc())
    p("```")

with open(OUT, "w") as f:
    f.write("\n".join(lines))
print("wrote", OUT)
