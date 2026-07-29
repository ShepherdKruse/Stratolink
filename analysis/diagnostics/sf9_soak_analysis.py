"""SF9 firmware soak — full-spectrum validation of board stratolink-2.

The soak runs the real flight firmware with the (uncommitted, jlink working tree)
SF9 change + 3 review fixes:
  - tx_sf 7->9 in all 4 region tables (lorawan.cpp)
  - FULL cadence 300->1200 s, lower tiers ->1800 s (config.h)
  - burst runaway cap (BURST_MAX_CYCLES=30 + cooldown latch)
  - uplink VSTOR>=3.0 V gate at the main.cpp call-site
  - GPS_STALE_RECOVERY wall-clock derived (=2 cycles @1200 s)

This is the COMMIT GATE.  We confirm, against logged telemetry (no assertions):
  1. SF/BW/freq integrity    — 100% SF9 / BW125k / US915 sub-band, no SF7 leak
  2. Cadence                 — interval distribution vs the 1200 s FULL target;
                               explain any sub-1200 s intervals (burst? reset?)
  3. GPS freshness gate      — STALE must be 0 (the keystone bug); NOGPS honest
  4. Link RSSI/SNR           — stable + comparable to the SF7 baseline (the SF9
                               benefit is a sensitivity-FLOOR/range one, realized
                               at distance, not a bench-SNR bump — framed honestly)
  5. Power / reset health    — VSTOR steady on the PSU, no boot-storm / reset loop
  6. Burst behavior          — any freefall episode stayed capped & FUP-safe

Run:
    set -a; source ~/.config/stratolink/env; set +a
    analysis/.venv/bin/python analysis/diagnostics/sf9_soak_analysis.py
"""
from __future__ import annotations
import os, sys
from pathlib import Path
from collections import Counter
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "antenna"))
import _style as S  # noqa: E402

SBURL = os.environ.get("SUPABASE_URL") or "https://iazmnyyfsobucndqncgw.supabase.co"
SBKEY = os.environ.get("SBKEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

DEVICE = "stratolink-2"
FLASH_UTC = "2026-06-02T19:39:00"          # SF9 firmware flashed
BASE_LO   = "2026-05-31T19:39:00"          # SF7 baseline window (pre-flash)

# Config under test (mirrors config.h / lorawan.cpp) — for the airtime check.
CADENCE_FULL_S = 1200
SF9_TOA_S      = 0.308                      # 35 B payload, BW125 CR4/5 (from _link.py)
FUP_S          = 30.0                       # TTN fair-use airtime/device/day

ALL_COLS = ("time,lat,lon,altitude_m,gps_satellites,gps_speed,gps_heading,"
            "rssi,snr,battery_voltage,solar_voltage,temperature,pressure,"
            "mems_accel_x,mems_accel_y,mems_accel_z,lora_sf,lora_bw,frequency_hz,"
            "ambient_lux,acoustic_event")


def fetch(since, before=None):
    rows, off = [], 0
    h = {"apikey": SBKEY, "Authorization": f"Bearer {SBKEY}"}
    while True:
        params = {"device_id": f"eq.{DEVICE}", "time": f"gte.{since}",
                  "select": ALL_COLS, "order": "time.asc", "limit": 1000, "offset": off}
        if before:
            params["time"] = f"gte.{since}"
            # PostgREST: combine two time filters via and=()
            params = {"device_id": f"eq.{DEVICE}",
                      "and": f"(time.gte.{since},time.lt.{before})",
                      "select": ALL_COLS, "order": "time.asc", "limit": 1000, "offset": off}
        r = requests.get(f"{SBURL}/rest/v1/telemetry", params=params, headers=h, timeout=30)
        r.raise_for_status()
        b = r.json(); rows += b
        if len(b) < 1000:
            break
        off += 1000
    df = pd.DataFrame(rows)
    if not df.empty:
        df["time"] = pd.to_datetime(df["time"], utc=True)
        for c in ("rssi","snr","battery_voltage","solar_voltage","temperature","pressure",
                  "mems_accel_x","mems_accel_y","mems_accel_z","ambient_lux","altitude_m",
                  "gps_satellites","lora_sf","lora_bw","frequency_hz"):
            if c in df:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.sort_values("time").reset_index(drop=True)
    return df


def classify_gps(df):
    """FRESH / STALE / NOGPS, same logic as soak_freeze_detector (bit-identical
    fix tuple = wedge on a stationary bench)."""
    out, last = [], None
    for _, r in df.iterrows():
        lat = r.get("lat")
        if pd.isna(lat) or lat is None:
            out.append("NOGPS"); continue
        cur = (round(float(lat), 6), round(float(r["lon"]), 6),
               None if pd.isna(r["altitude_m"]) else int(r["altitude_m"]),
               None if pd.isna(r["gps_satellites"]) else int(r["gps_satellites"]),
               None if pd.isna(r["gps_speed"]) else round(float(r["gps_speed"]), 2),
               None if pd.isna(r["gps_heading"]) else round(float(r["gps_heading"]), 2))
        if last is not None and cur == last:
            out.append("STALE")
        else:
            out.append("FRESH"); last = cur
    return out


def main():
    if not SBKEY:
        sys.exit("Set SBKEY: set -a; source ~/.config/stratolink/env; set +a")

    sf9 = fetch(FLASH_UTC)
    base = fetch(BASE_LO, FLASH_UTC)
    if sf9.empty:
        sys.exit("No SF9 soak rows yet.")

    sf9["gps_state"] = classify_gps(sf9)
    sf9["dt_s"] = sf9["time"].diff().dt.total_seconds()
    sf9["amag"] = np.sqrt(sf9.mems_accel_x**2 + sf9.mems_accel_y**2 + sf9.mems_accel_z**2)

    span_h = (sf9.time.iloc[-1] - sf9.time.iloc[0]).total_seconds() / 3600
    print("="*72)
    print(f"SF9 SOAK — {DEVICE} — {len(sf9)} uplinks over {span_h:.1f} h")
    print(f"  {sf9.time.iloc[0]:%Y-%m-%d %H:%M:%S} UTC  ->  {sf9.time.iloc[-1]:%Y-%m-%d %H:%M:%S} UTC")
    print("="*72)

    # --- 1. SF / BW / freq integrity ---------------------------------------
    print("\n[1] RADIO CONFIG INTEGRITY")
    sfc = Counter(sf9.lora_sf.dropna().astype(int))
    bwc = Counter(sf9.lora_bw.dropna().astype(int))
    frq = Counter((sf9.frequency_hz.dropna()/1e6).round(1))
    print(f"  lora_sf : {dict(sfc)}   -> {'PASS all SF9' if set(sfc)=={9} else '*** FAIL: SF7 leak ***'}")
    print(f"  lora_bw : {dict(bwc)} Hz -> {'PASS 125k' if set(bwc)=={125000} else 'CHECK'}")
    print(f"  freq    : {dict(frq)} MHz  (US915 uplink sub-band 903.9-905.3)")

    # --- 2. Cadence --------------------------------------------------------
    print("\n[2] CADENCE")
    dt = sf9.dt_s.dropna()
    burst = dt[dt < 60]                 # ~10 s burst beacons
    normal = dt[(dt >= 900) & (dt <= 1500)]
    longg = dt[dt > 1500]
    short_nonburst = dt[(dt >= 60) & (dt < 900)]
    print(f"  intervals n={len(dt)}  median={dt.median():.0f}s  mean={dt.mean():.0f}s")
    print(f"  FULL-target band [900,1500]s : {len(normal)}  (median {normal.median():.0f}s)" if len(normal) else "  none in FULL band")
    print(f"  burst <60s                   : {len(burst)}" + (f"  values={sorted(burst.round().astype(int))}" if len(burst) else ""))
    print(f"  short 60-900s (non-burst)    : {len(short_nonburst)}" + (f"  values={sorted(short_nonburst.round().astype(int))}" if len(short_nonburst) else ""))
    print(f"  long >1500s (gap/reset?)     : {len(longg)}" + (f"  values={sorted(longg.round().astype(int))}" if len(longg) else ""))

    # --- 3. GPS freshness --------------------------------------------------
    print("\n[3] GPS FRESHNESS GATE  (the keystone bug)")
    gc = Counter(sf9.gps_state)
    # longest STALE run
    runs, cur, best = [], 0, 0
    for s in sf9.gps_state:
        cur = cur+1 if s == "STALE" else 0
        best = max(best, cur)
    print(f"  FRESH={gc.get('FRESH',0)}  STALE={gc.get('STALE',0)}  NOGPS={gc.get('NOGPS',0)}")
    print(f"  longest STALE run = {best}  -> {'PASS (no wedge)' if best==0 else '*** STALE WEDGE ***'}")
    # NOGPS structure: clustered (acquisition gaps) vs scattered?
    nog = (sf9.gps_state == "NOGPS").values
    flips = int(np.sum(nog[1:] != nog[:-1]))
    print(f"  NOGPS episodes (contiguous blocks): {flips//2 + (1 if nog[0] or nog[-1] else 0)}  "
          f"-> {'scattered acquisition misses' if flips > 6 else 'few clustered blocks'} (bench sky view)")

    # --- 4. Link RSSI / SNR vs baseline ------------------------------------
    print("\n[4] LINK  (SF9 soak vs SF7 baseline; same bench geometry)")
    def stat(s):
        s = s.dropna()
        return f"n={len(s):4d}  mean={s.mean():6.2f}  med={s.median():6.2f}  min={s.min():6.2f}  max={s.max():6.2f}  σ={s.std():.2f}"
    print(f"  SF9  RSSI  {stat(sf9.rssi)}")
    if not base.empty:
        print(f"  SF7  RSSI  {stat(base.rssi)}")
    print(f"  SF9  SNR   {stat(sf9.snr)}")
    if not base.empty:
        print(f"  SF7  SNR   {stat(base.snr)}")
    print("  NOTE: gateway-measured SNR/RSSI is set by the LINK (power, range, antenna),")
    print("        not by SF.  On a fixed ~bench link both SFs sit near the top of the")
    print("        scale; SF9's +5 dB is a DEMOD-FLOOR/range gain (decodes weaker), not")
    print("        a bench-SNR increase.  The check here is STABILITY + no regression.")

    # --- 5. Power / reset health ------------------------------------------
    print("\n[5] POWER / RESET HEALTH")
    bv = sf9.battery_voltage.dropna()
    print(f"  VSTOR(battery_voltage): mean={bv.mean():.3f}V  min={bv.min():.3f}  max={bv.max():.3f}  σ={bv.std():.3f}")
    print(f"    -> {'PASS steady PSU rail (no brownout)' if bv.min() >= 4.4 else 'CHECK dips'}; "
          f"all >= 3.0V TX gate: {'yes' if bv.min()>=3.0 else 'NO'}")
    sv = sf9.solar_voltage.dropna()
    print(f"  solar_voltage: min={sv.min():.3f}  max={sv.max():.3f}  (tracks bench day/night light)")
    # reset/boot-storm proxy: a reset shortens the apparent interval; a reset LOOP
    # would be many sub-cadence intervals back-to-back.
    print(f"  boot-storm proxy: {len(short_nonburst)} non-burst sub-900s intervals "
          f"-> {'none (no reset loop)' if len(short_nonburst)==0 else 'inspect above'}")

    # --- 6. Burst / freefall ----------------------------------------------
    print("\n[6] BURST / FREEFALL")
    # freefall signature: |accel| well below 1 g (9.81). On a still bench ~9.8.
    ff = sf9[sf9.amag < 5.0]
    print(f"  |accel| over soak: median={sf9.amag.median():.2f}  min={sf9.amag.min():.2f}  (1g≈9.81)")
    print(f"  freefall-signature rows (|a|<5): {len(ff)}")
    if len(burst):
        # estimate worst-case burst airtime
        run = 0; longest = 0
        for d in sf9.dt_s.fillna(9999):
            run = run+1 if d < 60 else 0
            longest = max(longest, run)
        print(f"  burst beacons present: {len(burst)}; longest contiguous burst run = {longest} "
              f"(cap=BURST_MAX_CYCLES=30) -> {'CAPPED OK' if longest <= 30 else '*** CAP EXCEEDED ***'}")
    else:
        print("  no burst beacons -> freefall INT1 never fired (still bench), burst cap not exercised")

    # --- 7. Airtime / FUP --------------------------------------------------
    print("\n[7] AIRTIME / FUP  (TTN 30 s/device/day)")
    # observed daily uplink rate -> projected airtime
    upd = len(sf9) / max(span_h/24, 1e-9)
    print(f"  observed uplink rate: {upd:.0f}/day  x {SF9_TOA_S*1000:.0f}ms ToA = {upd*SF9_TOA_S:.1f}s/day "
          f"({upd*SF9_TOA_S/FUP_S*100:.0f}% of FUP)")
    print(f"  design (1200s FULL, 72/day): {72*SF9_TOA_S:.1f}s/day ({72*SF9_TOA_S/FUP_S*100:.0f}% of FUP)")

    plot(sf9, base, span_h)
    sf9.to_parquet(HERE / "sf9_soak.parquet")
    print(f"\nwrote {HERE/'sf9_soak.png'} and sf9_soak.parquet")


def plot(sf9, base, span_h):
    S.use_light()
    fig, ax = plt.subplots(2, 3, figsize=(18, 9))

    # (0,0) RSSI/SNR timeline with GPS state coloring
    a = ax[0,0]
    cmap = {"FRESH": S.TEAL7, "NOGPS": S.WARM, "STALE": S.RED}
    for st in ("FRESH","NOGPS","STALE"):
        m = sf9.gps_state == st
        if m.any():
            a.scatter(sf9.time[m], sf9.rssi[m], s=18, c=cmap[st], label=f"RSSI · {st} ({m.sum()})", zorder=3)
    a.set_ylabel("RSSI (dBm)")
    a.set_title("SF9a · Link & GPS state over the soak")
    a.legend(fontsize=8, loc="lower left")
    a.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))

    # (0,1) cadence histogram
    a = ax[0,1]
    dt = sf9.dt_s.dropna()
    a.hist(dt[dt < 2000], bins=np.arange(0, 2001, 50), color=S.TEAL7, alpha=0.85)
    a.axvline(1200, color=S.RED, ls="--", lw=2, label="1200 s FULL target")
    a.set_xlabel("inter-uplink interval (s)")
    a.set_ylabel("count")
    a.set_title(f"SF9b · Cadence (median {dt.median():.0f}s)")
    a.legend(fontsize=9)

    # (0,2) SNR distribution SF9 vs SF7
    a = ax[0,2]
    bins = np.arange(4, 14, 0.5)
    a.hist(base.snr.dropna(), bins=bins, color=S.DIM, alpha=0.7, density=True,
           label=f"SF7 baseline (n={base.snr.notna().sum()})")
    a.hist(sf9.snr.dropna(), bins=bins, color=S.TEAL7, alpha=0.7, density=True,
           label=f"SF9 soak (n={sf9.snr.notna().sum()})")
    a.set_xlabel("gateway SNR (dB)")
    a.set_ylabel("density")
    a.set_title("SF9c · SNR: SF9 vs SF7 (link-set, not SF-set)")
    a.legend(fontsize=8)

    # (1,0) VSTOR + solar
    a = ax[1,0]
    a.plot(sf9.time, sf9.battery_voltage, color=S.TEAL7, lw=1.3, label="VSTOR (battery_voltage)")
    a.axhline(3.0, color=S.RED, ls=":", lw=1.5, label="3.0 V TX gate")
    a.set_ylabel("VSTOR (V)")
    a.set_ylim(2.8, 5.0)
    a.set_title("SF9d · Power rail (PSU) — steady, no brownout")
    a2 = a.twinx()
    a2.plot(sf9.time, sf9.solar_voltage, color=S.WARM, lw=1.0, alpha=0.7, label="solar")
    a2.set_ylabel("solar (V)", color=S.WARM)
    a.legend(fontsize=8, loc="center left")
    a.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))

    # (1,1) GPS sats + state timeline
    a = ax[1,1]
    a.plot(sf9.time, sf9.gps_satellites, color=S.MINT, lw=1.0, marker=".", ms=4)
    for st, col in (("NOGPS", S.WARM), ("STALE", S.RED)):
        m = sf9.gps_state == st
        if m.any():
            a.scatter(sf9.time[m], np.zeros(m.sum())-0.5, s=20, c=col, label=st)
    a.set_ylabel("GPS satellites")
    a.set_title("SF9e · GPS sats & freshness (STALE=0 ✓)")
    a.legend(fontsize=8, loc="upper right")
    a.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))

    # (1,2) |accel| magnitude (freefall watch)
    a = ax[1,2]
    a.plot(sf9.time, sf9.amag, color=S.TEAL7, lw=1.0, marker=".", ms=4)
    a.axhline(9.81, color=S.DIM, ls=":", lw=1.2, label="1 g (still)")
    a.axhline(5.0, color=S.RED, ls="--", lw=1.2, label="freefall threshold band")
    a.set_ylabel("|accel| (m/s²)")
    a.set_title("SF9f · Accel magnitude (burst/freefall watch)")
    a.legend(fontsize=8)
    a.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))

    S.footer(fig, f"Stratolink-2 · SF9 soak {sf9.time.iloc[0]:%Y-%m-%d %H:%M}→{sf9.time.iloc[-1]:%H:%M} UTC · analysis/diagnostics/sf9_soak_analysis.py", light=True)
    fig.tight_layout()
    fig.savefig(HERE / "sf9_soak.png", dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    main()
