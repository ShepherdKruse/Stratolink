"""Overnight PPK2 bench profile of Stratolink-2 (board #2, flight firmware).

Reads the snapshots the unattended collector writes to
~/stratolink_overnight/windows.csv and turns them into the empirical power
picture, then ties it to the flight energy budget (relay_power_budget.py).

What is TRUSTWORTHY here (verified over 74 clean snapshots):
- STOP1 sleep floor, remarkably stable (~33 uA, stdev < 1 uA).
- ~92% of wall-clock asleep.
NOT trustworthy: any "active" current level, clean or dirty (see below).

Honesty notes baked into the figure:
- The floor is measured with the J-Link SWD debugger ATTACHED, which keeps the
  debug power domain alive.  So ~32 uA is an UPPER BOUND on the true flight
  STOP1 floor, not the flight number.  The model assumes 4 uA (DOCUMENTATION.md,
  typical STM32WL STOP1).  The gap (~28 uA) is the debugger domain.  Confirming
  the true floor needs a debugger-OFF capture (J-Link on the hub so it can be
  powered down); that is a Teddy-at-the-bench task.
- The board is bench-powered at a fixed 4.66 V rail and its VSTOR ADC reads
  ~20% low (3704 mV all night, board_state.csv).  That puts the tier logic at
  REDUCED, so the board self-selects the 1800 s sleep interval, not the 1200 s
  FULL flight cadence.  It is NOT running a representative flight duty cycle
  (it has not rejoined TTN).  GPS/TX phase currents therefore still come from
  the datasheet, not this bench run.
- The 14 high-artifact snapshots are a MIXTURE, not garbage and not a clean
  burst measurement.  The J-Link morning read (region_known=false all night,
  reset cause BOR+PIN only so zero watchdog resets, relay/CTT/TX stats all
  zero) proves the board cycled wake -> ~30 s GPS acquisition -> STOP1 sleep
  with the GNSS-first RF-quiet gate held.  A handful of snapshots SHOULD
  therefore have caught a GPS window (expected 3-5, see the printed catch-rate
  check).  A catch steps the rail current from ~33 uA to ~20 mA and the PPK2
  range switch then corrupts the rest of the stream: identical quantized
  p99/max plateaus (61.3 / 245 mA) across all 14 windows plus ~44% sample
  loss, so a real GPS catch and a spontaneous stream desync leave the SAME
  fingerprint.  But the observed count (14) is ~3x the catch expectation and
  the timing fits no firmware cadence (five gaps of 578-626 s between
  high-artifact windows are shorter than any 1200/1800 s cycle; their phases
  mod 1200 are scattered).  So the set almost surely CONTAINS the expected
  few real GPS catches (P(zero catches) < 4%) with artifact-corrupted tails,
  but most of the 14 are spontaneous desyncs, and no individual window can be
  labeled.  All 14 stay EXCLUDED from the duty/mean statistics; in aggregate
  they are consistent with the cycle running, nothing stronger.

Light theme (Teddy's 4nec2 preference).  Re-run any time.
"""
from __future__ import annotations
from pathlib import Path
import sys, csv

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "antenna"))
import _style as S
S.use_light()

WINDOWS = Path.home() / "stratolink_overnight" / "windows.csv"

# --- flight energy-budget constants (identical to relay_power_budget.py) ------
V_RAIL, ETA = 3.3, 0.85
E_CAP = 8.86  # J to conservative 3.32 V reported-plateau endpoint, nominal 1 F
I_GPS, I_MCU, I_TX14 = 0.030, 0.005, 0.044
T_GPS_HOT, TOA_SF9 = 2.0, 0.308
CADENCE = 1200.0
CYC_DAY = 86400 / CADENCE
IDLE = CADENCE - T_GPS_HOT - TOA_SF9
MODEL_SLEEP_UA = 4.0              # STOP1 assumption we are substantiating


def p(I):
    return I * V_RAIL / ETA


def load():
    if not WINDOWS.exists():
        print(f"no data yet at {WINDOWS}"); return []
    rows = []
    with open(WINDOWS) as f:
        for r in csv.DictReader(f):
            try: rows.append({k: float(v) for k, v in r.items()})
            except ValueError: pass
    return rows


def daily_energy(sleep_ua):
    e_gps = p(I_GPS + I_MCU) * T_GPS_HOT * CYC_DAY
    e_tx = p(I_TX14) * TOA_SF9 * CYC_DAY
    e_sleep = p(sleep_ua * 1e-6) * IDLE * CYC_DAY
    return e_gps, e_tx, e_sleep


def main():
    rows = load()
    n = len(rows)
    print(f"accepted snapshots: {n}")
    if n == 0:
        print("nothing to plot yet"); return

    # A window with a raised artifact fraction had its stream corrupted partway
    # through: misaligned samples slip under the 250 mA hard filter and pile up
    # at quantized levels (identical p99 ~61 mA / max ~245 mA fingerprints
    # across ALL such windows, plus ~44% sample loss).  Two triggers produce
    # this same fingerprint: a real GPS-acquisition catch (the ~20 mA current
    # step makes the PPK2 switch ranges, which desyncs the stream and eats the
    # tail of the window) and a spontaneous desync of the fragile sample
    # stream.  The catch-rate check below shows the observed count is ~3x the
    # GPS-catch expectation, so both are present and no window can be labeled
    # individually.  The bottom-20% floor is robust either way, but the mean
    # and the "active" tail are not.  Clean windows sit at ~0.3% artifacts;
    # corrupted ones jump to ~3%.  Split at 1%.
    CLEAN_ART = 0.01
    clean = [r for r in rows if r["art_frac"] <= CLEAN_ART]
    dirty = [r for r in rows if r["art_frac"] > CLEAN_ART]
    print(f"clean windows: {len(clean)}  high-artifact (excluded from duty/mean): {len(dirty)}")

    # --- GPS-window catch-rate check ------------------------------------------
    # J-Link 2026-07-24: region_known=false all night (indoors, no fix), reset
    # cause BOR+PIN only.  So every cycle ran wake -> 30 s GPS acquisition ->
    # sleep, RF silent.  P(a 40 s snapshot overlaps a 30 s GPS window) is
    # (40+30)/cycle.  The bench VSTOR ADC read 3704 mV all night = REDUCED
    # tier = 1800 s sleep + ~32 s wake, but both cadences are shown.
    SNAP_LEN, GPS_LEN = 40.0, 30.0
    for cyc_s, tag in ((CADENCE, "FULL 1200 s (flight cadence)"),
                       (1832.0, "REDUCED 1800 s sleep + 32 s wake (bench tier)")):
        p_catch = (SNAP_LEN + GPS_LEN) / cyc_s
        print(f"catch-rate @ {tag}: {p_catch*100:.1f}%/snapshot, "
              f"expected {p_catch*n:.1f} of {n} vs {len(dirty)} high-artifact observed")
    if dirty:
        act = float(np.mean([r["active_mean_ua"] for r in dirty]))
        act_3v3 = act * 4.66 / V_RAIL * ETA
        print(f"high-artifact active mean {act/1e3:.1f} mA at 4.66 V rail = "
              f"{act_3v3/1e3:.1f} mA at 3.3 V, vs 30-35 mA GPS-acq + MCU model: "
              f"GPS-order, but a mixture average, not a measured phase current")
        print("verdict: high-artifact set = a few real GPS catches (tails "
              "artifact-corrupted) + spontaneous desyncs, individually "
              "unlabelable; all excluded from clean stats")

    # floor is robust across ALL windows (bottom 20% is the true sleep population)
    floor = np.array([r["floor_ua"] for r in rows])
    tf = np.array([r["ts"] for r in rows]); tf = (tf - tf.min()) / 3600.0  # hours
    # clean-only duty/mean statistics
    median = np.array([r["median_ua"] for r in clean])
    sleep = np.array([r["frac_sleep"] for r in clean]) * 100
    mean = np.array([r["mean_ua"] for r in clean])
    t = (np.array([r["ts"] for r in clean]) - rows[0]["ts"]) / 60.0

    f_med, f_sd = float(np.median(floor)), float(np.std(floor))
    # Floor drift: flattening (a benign settling transient) vs linear or
    # accelerating (a real growing leak). Compare first-half vs second-half
    # slope. Note the MECHANISM of the settle is undetermined: board self-heat
    # is ~0.93 mW (0.1 C, 10x too small to move the floor this much), so it is
    # instrument warm-up, bias settling, or ambient, not board thermal load.
    # The non-increasing shape is what matters: it rules out a growing leak.
    drift = float(np.polyfit(tf, floor, 1)[0]) if len(tf) > 2 else 0.0
    h = len(tf) // 2
    d1 = float(np.polyfit(tf[:h], floor[:h], 1)[0]) if h > 2 else 0.0
    d2 = float(np.polyfit(tf[h:], floor[h:], 1)[0]) if len(tf) - h > 2 else 0.0
    settling = abs(d2) < abs(d1) * 0.6
    print(f"floor {f_med:.2f} +/- {f_sd:.2f} uA  drift {drift*1000:.0f} nA/h "
          f"(1st half {d1*1000:.0f}, 2nd {d2*1000:.0f} -> "
          f"{'flattening/settling' if settling else 'linear/watch'}) | "
          f"clean median {np.median(median):.1f} | sleep {np.median(sleep):.1f}% | "
          f"clean mean {np.median(mean):.0f} uA")

    fig, ax = plt.subplots(1, 3, figsize=(14.5, 4.6))
    fig.suptitle(f"Stratolink-2 overnight bench profile  (PPK2 4.66 V, flight firmware, "
                 f"{len(clean)} clean of {n} snapshots)")

    # --- Panel A: sleep-floor stability + drift vs the 4 uA flight assumption --
    a = ax[0]
    a.plot(tf, floor, "o", color=S.TEAL7, ms=4, label="bench floor (debugger ON)")
    a.axhspan(MODEL_SLEEP_UA, f_med, color=S.WARM, alpha=0.12)
    a.annotate("debugger power domain\n(~28 uA, absent in flight)",
               xy=(tf.min() + (tf.max() - tf.min()) * 0.22,
                   (MODEL_SLEEP_UA + f_med) / 2), fontsize=7.5,
               color=S.TEXT_DIM, ha="center", va="center")
    # drift trend, per-half so the flattening settle is visible
    mid = tf[h]
    a.plot([tf.min(), mid], np.polyval(np.polyfit(tf[:h], floor[:h], 1),
           [tf.min(), mid]), color=S.MINT, lw=1.3,
           label=f"drift {d1*1000:.0f}->{d2*1000:.0f} nA/h ({'settling' if settling else 'watch'})")
    a.plot([mid, tf.max()], np.polyval(np.polyfit(tf[h:], floor[h:], 1),
           [mid, tf.max()]), color=S.MINT, lw=1.3)
    a.axhline(MODEL_SLEEP_UA, color=S.RED, lw=1.6, ls="--",
              label=f"flight model STOP1 = {MODEL_SLEEP_UA:.0f} uA")
    a.set_ylim(0, max(floor) * 1.15)
    a.set_xlabel("hours into run"); a.set_ylabel("sleep-floor current (uA)")
    a.set_title(f"A - STOP1 floor settling to {f_med:.0f} uA, no leak")
    a.legend(fontsize=7.5, loc="center right")  # upper right hides the 2nd-half points

    # --- Panel B: per-window mean-current distribution (CLEAN windows only) ----
    b = ax[1]
    b.hist(mean, bins=np.linspace(min(mean) * 0.95, max(mean) * 1.05, 18),
           color=S.TEAL10, alpha=0.85, edgecolor=S.GRID)
    b.axvline(float(np.median(mean)), color=S.MINT, lw=1.4,
              label=f"median {np.median(mean):.0f} uA")
    b.set_xlabel("per-window mean current (uA)")
    b.set_ylabel("clean windows")
    b.set_title("B - tight deep-sleep cluster (clean windows)")
    b.text(0.97, 0.80, f"{len(dirty)} high-artifact windows excluded:\n"
           "GPS-catch candidates + stream desyncs,\n"
           "same fingerprint, means invalid",
           transform=b.transAxes, ha="right", va="top", fontsize=7.5,
           color=S.TEXT_DIM)
    b.legend(fontsize=7.5, loc="upper right")

    # --- Panel C: daily energy budget, sleep floor bracketed ------------------
    c = ax[2]
    g, tx, s4 = daily_energy(MODEL_SLEEP_UA)
    _, _, s32 = daily_energy(f_med)
    comps = ["GPS acq\n(2s/cyc)", "LoRaWAN TX\n(SF9)", "STOP1 sleep\n4 uA (flight)"]
    vals = [g, tx, s4]
    yy = np.arange(len(comps))
    c.barh(yy, vals, color=[S.TEAL7, S.TEAL10, S.MINT], alpha=0.9)
    for i, v in enumerate(vals):
        c.text(v + 0.3, i, f"{v:.1f} J", va="center", fontsize=9, fontweight="bold")
    # overlay: what sleep would cost at the bench-measured 32 uA (if it were real)
    c.barh(len(comps), s32, color=S.WARM, alpha=0.55)
    c.text(s32 + 0.3, len(comps), f"{s32:.1f} J", va="center", fontsize=9)
    comps2 = comps + [f"sleep at bench\n{f_med:.0f} uA (debugger)"]
    c.set_yticks(np.arange(len(comps2))); c.set_yticklabels(comps2, fontsize=8)
    c.invert_yaxis()
    c.set_xlabel("energy the harvester must replace (J/day)")
    c.set_title(f"C - GPS dominates; sleep is {s4/(g+tx+s4)*100:.0f}% at 4 uA")

    S.footer(fig, f"overnight_bench_profile.py  N={n}  floor {f_med:.1f}+/-{f_sd:.2f} uA "
                  f"(debugger ON, flight expects ~{MODEL_SLEEP_UA:.0f} uA)  "
                  f"GPS/TX from datasheet  cadence {CADENCE:.0f}s", light=True)
    fig.tight_layout(rect=[0, 0.02, 1, 0.95])
    out = HERE / "overnight_bench_profile.png"
    fig.savefig(out, dpi=150)
    print("wrote", out)
    print(f"\ndaily energy (flight, 4 uA sleep): GPS {g:.1f} + TX {tx:.1f} + sleep {s4:.1f} "
          f"= {g+tx+s4:.1f} J/day")
    print(f"if sleep floor were the bench 32 uA: sleep {s32:.1f} J/day "
          f"(+{s32-s4:.1f} J, +{(s32-s4)/(g+tx+s4)*100:.0f}% of budget)")


if __name__ == "__main__":
    main()
