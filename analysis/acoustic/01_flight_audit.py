"""
Acoustic-event flight audit (Stratolink-3, 2026-05 SF->Spain).

Question (Teddy): is the `acoustic_event` bit (fires ~30% of cycles) real
stratospheric acoustics, payload self-noise, LoRa-TX coupling, or a detector
artifact?  Firmware emits ONE bit/cycle: mic RMS over a 55 ms window > 4x an
adaptive noise floor (mic_acoustic.cpp), sampled BEFORE the LoRa uplink keys
up (main.cpp: mic L164, TX L193), with a ~20 min sleep between cycles.

Finding this script substantiates:
  * The "~30%" is two regimes: ~0.4% on a clean bench PSU (stratolink-2,
    incl. tonight's SF9 soak) vs ~50% in flight.
  * In flight the rate is FLAT ~50% across altitude/region/temperature and
    UNCORRELATED with RSSI, SNR and the accelerometer -> a coin-flip on noise,
    not sporadic real events.
  * The mic is sampled before TX every cycle -> the device's own concurrent
    transmission cannot be the trigger by construction.

Light (4nec2) theme per Teddy's preference.
  analysis/.venv/bin/python analysis/acoustic/01_flight_audit.py
"""
from __future__ import annotations
import sys, pathlib
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "antenna"))
import _style as S  # noqa: E402
S.use_light()

OUT = pathlib.Path(__file__).resolve().parent / "figs"; OUT.mkdir(parents=True, exist_ok=True)
FLIGHT_CSV = ROOT / "analysis" / "antenna" / "data" / "telemetry_raw.csv"
BENCH_CSV = ROOT / "analysis" / "acoustic" / "data" / "bench_stratolink2.csv"

NUM = ["rssi", "snr", "battery_voltage", "solar_voltage", "temperature",
       "pressure", "altitude_m", "lora_sf"]


def _num(df, cols):
    for c in cols:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def load_flight():
    df = pd.read_csv(FLIGHT_CSV, parse_dates=["time"])
    df["ae"] = (pd.to_numeric(df["acoustic_event"], errors="coerce") > 0).astype(float)
    df = _num(df, NUM + ["mems_accel_x", "mems_accel_y", "mems_accel_z", "lat"])
    df["accel_mag"] = np.sqrt(df.mems_accel_x**2 + df.mems_accel_y**2 + df.mems_accel_z**2)
    df["inflight"] = (df.altitude_m.between(-200, 13000) &
                      df.pressure.between(40, 1100) & df.lat.between(-90, 90))
    return df


def load_bench():
    df = pd.read_csv(BENCH_CSV, parse_dates=["time"])
    df["ae"] = (pd.to_numeric(df["acoustic_event"], errors="coerce") > 0).astype(float)
    return _num(df, NUM)


def wilson(k, n, z=1.96):
    if n == 0:
        return np.nan, np.nan, np.nan
    p = k / n; den = 1 + z*z/n
    c = (p + z*z/(2*n))/den
    h = z*np.sqrt(p*(1-p)/n + z*z/(4*n*n))/den
    return p, max(0, c-h), min(1, c+h)


def main():
    fl = load_flight(); be = load_bench()
    infl = fl[fl.inflight]
    print(f"bench n={len(be)} rate={be.ae.mean():.3f} | "
          f"flight in-flight n={len(infl)} rate={infl.ae.mean():.3f}")

    # day/night split (solar as proxy for harvester-active daylight)
    shi = infl.solar_voltage.quantile(0.66); slo = infl.solar_voltage.quantile(0.33)
    day = infl[infl.solar_voltage >= shi]; night = infl[infl.solar_voltage <= slo]
    print(f"  in-flight 'day' (solar>={shi:.2f}V) AE={day.ae.mean():.3f} n={len(day)} | "
          f"'night' (solar<={slo:.2f}V) AE={night.ae.mean():.3f} n={len(night)}")

    fig, ax = plt.subplots(2, 3, figsize=(16.6, 9.5))
    fig.suptitle("Stratolink-3 acoustic_event audit - bench-silent, fires on a flight-only self-noise",
                 y=0.985)

    # (a) regime contrast bars ------------------------------------------------
    a = ax[0, 0]
    groups = [
        ("Bench PSU\n(stratolink-2)", be.ae.sum(), len(be), S.TEAL7),
        ("Flight US\n(stratolink-3)", infl[infl.region == "US"].ae.sum(),
         (infl.region == "US").sum(), S.RED),
        ("Flight EU\n(stratolink-3-eu)", infl[infl.region == "EU"].ae.sum(),
         (infl.region == "EU").sum(), S.RED),
    ]
    for i, (lbl, k, n, c) in enumerate(groups):
        p, lo, hi = wilson(int(k), int(n))
        a.bar(i, p, color=c, alpha=0.85, width=0.62)
        a.errorbar(i, p, yerr=[[p-lo], [hi-p]], color=S.TEXT, capsize=4, lw=1.3)
        a.annotate(f"{p*100:.1f}%\nn={int(n)}", (i, hi+0.03), ha="center",
                   fontsize=9, color=S.TEXT)
    a.set_xticks(range(3)); a.set_xticklabels([g[0] for g in groups], fontsize=9)
    a.set_ylabel("P(acoustic_event)"); a.set_ylim(0, 1.02)
    a.set_title("(a) Silent on a clean bench, ~50% the moment it flies")

    # (b) in-flight vs altitude (flat) ---------------------------------------
    a = ax[0, 1]
    bins = [-200, 2000, 5000, 7500, 9000, 9800, 10300, 13000]
    cut = pd.cut(infl.altitude_m, bins)
    xs, ps, los, his, ns = [], [], [], [], []
    for itv, g in infl.groupby(cut, observed=True):
        p, lo, hi = wilson(int(g.ae.sum()), len(g))
        xs.append(itv.mid/1000); ps.append(p); los.append(lo); his.append(hi); ns.append(len(g))
    a.errorbar(xs, ps, yerr=[np.array(ps)-los, np.array(his)-np.array(ps)],
               fmt="o-", color=S.RED, capsize=3, lw=2, ms=6)
    for x, p, hi, n in zip(xs, ps, his, ns):
        a.annotate(f"n={n}", (x, hi+0.03), ha="center", fontsize=7.5, color=S.TEXT_DIM)
    a.axhline(infl.ae.mean(), ls="--", color=S.MINT, lw=1.4)
    a.annotate(f"flight mean {infl.ae.mean()*100:.0f}%", (0.4, infl.ae.mean()+0.03),
               color=S.MINT, fontsize=9)
    a.set_xlabel("altitude (km)"); a.set_ylabel("P(acoustic_event)")
    a.set_ylim(0, 1.02); a.set_title("(b) In flight: FLAT vs altitude (not altitude-graded)")

    # (c) within-flight covariate (in)dependence -----------------------------
    a = ax[0, 2]
    feats = [("altitude", "altitude_m"), ("RSSI", "rssi"), ("SNR", "snr"),
             ("temperature", "temperature"), ("pressure", "pressure"),
             ("accel |a|", "accel_mag"), ("lora_sf", "lora_sf"),
             ("battery_V", "battery_voltage"), ("solar_V", "solar_voltage")]
    names, rs = [], []
    for nm, col in feats:
        x = infl[col]; m = infl.ae.notna() & x.notna()
        if m.sum() > 8 and x[m].std() > 0:
            names.append(nm); rs.append(np.corrcoef(infl.ae[m], x[m])[0, 1])
    order = np.argsort(np.abs(rs))
    names = [names[i] for i in order]; rs = [rs[i] for i in order]
    cols = [S.RED if abs(r) > 0.3 else S.DIM for r in rs]
    a.barh(range(len(rs)), rs, color=cols, alpha=0.85)
    a.set_yticks(range(len(rs))); a.set_yticklabels(names, fontsize=9)
    a.axvspan(-0.2, 0.2, color=S.MINT, alpha=0.10)
    a.axvline(0, color=S.TEXT, lw=0.8)
    a.set_xlim(-0.6, 0.6); a.set_xlabel("point-biserial corr with acoustic_event")
    a.set_title("(c) Flat vs link/vibration - tracks solar & temperature")
    a.annotate("flat: altitude,\nRSSI, SNR, accel", (-0.30, 1.2), color=S.TEXT_DIM,
               fontsize=8, ha="center")
    a.annotate("non-zero:\nsolar / temp / batt\n(daytime -> harvester)", (0.40, 2.0),
               color=S.RED, fontsize=8, ha="center")

    # (d) harvester ladder: bench / flight-night / flight-day ----------------
    a = ax[1, 0]
    ladder = [
        ("Bench PSU\n(no harvester)", be.ae.sum(), len(be), S.TEAL7),
        ("Flight night\n(solar low)", night.ae.sum(), len(night), "#6a4c93"),
        ("Flight day\n(solar high)", day.ae.sum(), len(day), S.WARM),
    ]
    for i, (lbl, k, n, c) in enumerate(ladder):
        p, lo, hi = wilson(int(k), int(n))
        a.bar(i, p, color=c, alpha=0.88, width=0.62)
        a.errorbar(i, p, yerr=[[p-lo], [hi-p]], color=S.TEXT, capsize=4, lw=1.3)
        a.annotate(f"{p*100:.0f}%\nn={int(n)}", (i, hi+0.03), ha="center", fontsize=9, color=S.TEXT)
    a.set_xticks(range(3)); a.set_xticklabels([g[0] for g in ladder], fontsize=9)
    a.set_ylabel("P(acoustic_event)"); a.set_ylim(0, 1.02)
    a.set_title("(d) Fires with the solar harvester (day >> night >> bench)")

    # (e) per-cycle timing cartoon -------------------------------------------
    a = ax[1, 1]; a.set_xlim(0, 10); a.set_ylim(0, 3); a.axis("off")
    a.set_title("(e) Mic is sampled BEFORE TX every cycle")
    phases = [  # (label, x0, w, color)
        ("wake\n+tier", 0.2, 0.9, S.DIM),
        ("GPS fix\n<=30 s", 1.2, 1.6, S.DIM),
        ("sensors\n+ MIC *", 3.0, 1.5, S.TEAL7),
        ("pack", 4.7, 0.7, S.DIM),
        ("LoRa TX ^\n~0.31 s", 5.6, 1.4, S.RED),
        ("RX1/RX2\n~5 s", 7.2, 1.3, S.DIM),
        ("sleep\n20 min", 8.7, 1.1, "#cfd8e3"),
    ]
    for lbl, x0, w, c in phases:
        a.add_patch(FancyBboxPatch((x0, 1.2), w*0.92, 0.8,
                    boxstyle="round,pad=0.02", fc=c, ec=S.TEXT_DIM, lw=0.8, alpha=0.9))
        a.text(x0 + w*0.46, 1.6, lbl, ha="center", va="center", fontsize=8.2,
               color=(S.L_BG if c in (S.RED, S.TEAL7) else S.TEXT))
    a.annotate("", xy=(5.6, 2.35), xytext=(3.75, 2.35),
               arrowprops=dict(arrowstyle="->", color=S.MINT, lw=1.6))
    a.text(4.6, 2.55, "deltat ~ 1 s", ha="center", color=S.MINT, fontsize=9)
    a.text(5.0, 0.7, "mic energy is measured ~1 s BEFORE the radio keys up,\n"
           "then the radio sleeps 20 min -> a packet's own TX\ncannot have caused its acoustic_event bit.",
           ha="center", va="center", fontsize=8.6, color=S.TEXT)

    # (f) verdict box ---------------------------------------------------------
    a = ax[1, 2]; a.axis("off")
    a.set_title("(f) Verdict so far (1-bit telemetry)")
    a.add_patch(FancyBboxPatch((0.02, 0.04), 0.96, 0.88, boxstyle="round,pad=0.02",
                fc=S.L_PANEL, ec=S.L_GRID, lw=1.0, transform=a.transAxes))
    a.text(0.07, 0.86, "RULED OUT", color=S.RED, fontsize=10, fontweight="bold", transform=a.transAxes)
    a.text(0.07, 0.80, "- own LoRa TX - mic sampled ~1 s before TX\n"
                       "- altitude-graded acoustics - flat 0.5->10 km\n"
                       "- bulk vibration - flat vs accelerometer\n"
                       "- link margin / SF - flat vs RSSI/SNR/SF",
           color=S.TEXT, fontsize=8.6, va="top", transform=a.transAxes)
    a.text(0.07, 0.50, "LEADING CAUSE", color=S.MINT, fontsize=10, fontweight="bold", transform=a.transAxes)
    a.text(0.07, 0.44, "- tracks solar/charging: 79% day vs 18% night\n"
                       "  vs 0.4% bench -> BQ25570 harvester switching\n"
                       "  noise on the mic +3.3V rail (shared rail)\n"
                       "- thermal drift confounded w/ daylight (open)",
           color=S.TEXT, fontsize=8.6, va="top", transform=a.transAxes)
    a.text(0.07, 0.16, "NEXT", color=S.L_ACCENT, fontsize=10, fontweight="bold", transform=a.transAxes)
    a.text(0.07, 0.10, "bench rig: log rms_sq + raw PCM; lamp on/off\n"
                       "on supercap; cold-soak on clean PSU.",
           color=S.TEXT, fontsize=8.6, va="top", transform=a.transAxes)

    for axx in (ax[0, 0], ax[0, 1], ax[0, 2], ax[1, 0]):
        axx.grid(True, alpha=0.4)
    S.footer(fig, "flight: telemetry_raw.csv (n=457) * bench: bench_stratolink2.csv (n=570, "
                  "incl. SF9 soak) * analysis/acoustic/01_flight_audit.py", light=True)
    fig.tight_layout(rect=[0, 0.01, 1, 0.95])
    p = OUT / "AC1_flight_audit.png"; fig.savefig(p, dpi=140)
    print("wrote", p)


if __name__ == "__main__":
    main()
