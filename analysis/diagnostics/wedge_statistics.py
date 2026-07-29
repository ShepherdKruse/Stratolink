#!/usr/bin/env python3
"""Statistical fingerprint of the GPS "wedge" across the Stratolink-3 flight.

Pulls every fix for both flight DevEUIs from Supabase, classifies each as
FRESH / STALE / NOGPS (STALE = position+sats+speed bit-identical to the prior
fix = the module re-shipping a frozen cache), then characterizes each STALE
burst ("wedge event") by:

  * onset gap   — cadence multiples since the last non-stale fix (≈1.0 = the
                  wedge began cleanly from a fresh fix, no erratic precursor)
  * recovery    — what the module did on un-wedging (FRESH vs NOGPS) and the
                  recovery gap in cadence multiples (≈1.0 = smooth self-recovery
                  on a normal cycle boundary, NO reboot; ≫1 = a real gap/reboot)
  * run length  — consecutive wedged cycles (the "stickiness")

The signature this surfaces — onset & recovery both snapped to the sleep/wake
cadence, recovery without a reboot, wildly variable sticky run-lengths — is the
fingerprint of a per-cycle stochastic WAKE failure, not an environmental or
radiation trigger.  See analysis/diagnostics/WAKE_WEDGE_ROOT_CAUSE.md.

Env: SUPABASE_URL, SBKEY (source ~/.config/stratolink/env).
Out: analysis/diagnostics/wedge_statistics.png  (run from repo root)
"""
import os, requests, pandas as pd, numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from datetime import datetime, timezone
SB=os.environ["SUPABASE_URL"]; K=os.environ["SBKEY"]; H={"apikey":K,"Authorization":f"Bearer {K}"}
rows=[]
for dev in ["stratolink-3","stratolink-3-eu"]:
    off=0
    while True:
        r=requests.get(f"{SB}/rest/v1/telemetry",params={"device_id":f"eq.{dev}","select":"time,lat,lon,altitude_m,pressure,temperature,gps_satellites,gps_speed,battery_voltage,solar_voltage","order":"time.asc","limit":1000,"offset":off},headers=H,timeout=30);r.raise_for_status()
        b=r.json();rows+=b
        if len(b)<1000:break
        off+=1000
df=pd.DataFrame(rows); df["time"]=pd.to_datetime(df["time"],utc=True,format="ISO8601")
df=df.sort_values("time").reset_index(drop=True)
LAUNCH=datetime(2026,5,17,15,55,tzinfo=timezone.utc)
df=df[df["time"]>=LAUNCH].reset_index(drop=True)
last=None;cls=[]
for _,r in df.iterrows():
    lat,lon,alt=r["lat"],r["lon"],r["altitude_m"];sats=r["gps_satellites"];spd=r["gps_speed"]
    if pd.isna(lat):cls.append("NOGPS");continue
    if abs(lat)>90:cls.append("GARBAGE");continue
    cur=(round(lat,6),round(lon,6),int(alt) if pd.notna(alt) else None,int(sats) if pd.notna(sats) else None,round(spd,2) if pd.notna(spd) else None)
    if last is not None and cur==last:cls.append("STALE")
    else:cls.append("FRESH");last=cur
df["cls"]=cls
df["dt_s"]=df["time"].diff().dt.total_seconds()
med_cad=df["dt_s"].median()
print(f"rows={len(df)}  median cadence={med_cad:.0f}s ({med_cad/60:.1f} min)")
print(f"class counts: {df['cls'].value_counts().to_dict()}")

bursts=[];i=0
while i<len(df):
    if df.at[i,"cls"]=="STALE":
        j=i
        while j<len(df) and df.at[j,"cls"]=="STALE":j+=1
        onset=df.at[i,"time"]; end=df.at[j-1,"time"]
        pre=[k for k in range(i-1,-1,-1) if df.at[k,"cls"]!="STALE"]
        onset_gap=(onset-df.at[pre[0],"time"]).total_seconds() if pre else None
        rec_cls=df.at[j,"cls"] if j<len(df) else "END"
        rec_gap=(df.at[j,"time"]-end).total_seconds() if j<len(df) else None
        bursts.append(dict(onset=onset,dur_min=(end-df.at[i,"time"]).total_seconds()/60,n=j-i,
                           onset_gap_x=(onset_gap/med_cad if onset_gap else None),rec_cls=rec_cls,
                           rec_gap_x=(rec_gap/med_cad if rec_gap else None),
                           T=df.at[i,"temperature"],alt=df.at[i,"altitude_m"],vbat=df.at[i,"battery_voltage"]))
        i=j
    else:i+=1

print(f"\n=== {len(bursts)} WEDGE EVENTS (STALE bursts) ===")
print(f"{'onset':17} {'dur_min':>7} {'cyc':>3} {'onset_gap':>9} {'recovery':>9} {'rec_gap':>8}")
for b in bursts:
    og="%.1f"%b["onset_gap_x"] if b["onset_gap_x"] else "-"
    rg="%.1f"%b["rec_gap_x"] if b["rec_gap_x"] else "-"
    print(f"{b['onset'].isoformat()[:16]:17} {b['dur_min']:>7.0f} {b['n']:>3} {og:>9} {b['rec_cls']:>9} {rg:>8}")

durs=np.array([b["dur_min"] for b in bursts])
print(f"\nburst durations (min): min={durs.min():.0f} median={np.median(durs):.0f} max={durs.max():.0f}")
onsets=[b["onset"] for b in bursts]
ints=[(onsets[k]-onsets[k-1]).total_seconds()/3600 for k in range(1,len(onsets))]
ints_leg=[round(x,1) for x in ints if x<24]
print(f"inter-onset intervals within a leg (h): {ints_leg}")
ogl=[round(b["onset_gap_x"],1) for b in bursts if b["onset_gap_x"]]
rgl=[round(b["rec_gap_x"],1) for b in bursts if b["rec_gap_x"]]
print(f"\nonset gaps (x cadence): {ogl}   (~1.0 = clean wedge straight from a fresh fix; no anomaly)")
print(f"recovery gaps (x cadence): {rgl}   (~1.0 = smooth self-recovery, NO reboot; >>1 = gap/reboot)")
print(f"recovery classes: {pd.Series([b['rec_cls'] for b in bursts]).value_counts().to_dict()}")
print(f"cycles per burst (sticky run lengths): {[b['n'] for b in bursts]}")

fig,ax=plt.subplots(1,3,figsize=(16,4.5))
ax[0].hist(durs,bins=12,color="#d62728");ax[0].set_title("Wedge duration (min)");ax[0].set_xlabel("min")
ax[1].hist(ints_leg,bins=10,color="#1f77b4");ax[1].set_title("Inter-onset interval / leg (h)");ax[1].set_xlabel("h")
ax[2].scatter(ogl,rgl,c="#2a9d4e",s=40);ax[2].axhline(1.5,ls=":",c="gray");ax[2].axvline(1.5,ls=":",c="gray")
ax[2].set_xlabel("onset gap (x cad)");ax[2].set_ylabel("recovery gap (x cad)");ax[2].set_title("clean wedge? smooth recovery?")
plt.tight_layout();plt.savefig("analysis/diagnostics/wedge_statistics.png",dpi=150,bbox_inches="tight")
print("\nwrote analysis/diagnostics/wedge_statistics.png")
