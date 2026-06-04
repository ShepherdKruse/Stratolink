#!/usr/bin/env python3
"""18.3 h phase-2 soak results: TTN supply/solar stability (left) and the Meshtastic
relay's cumulative forwarding (right). Substantiates the headline result of
PHASE2_FINAL_REPORT.md. Clean light style (matches the power-model figures).

Data: /tmp/soak.json (Supabase TTN rows) + relay s_relay snapshots (J-Link, this run).
"""
from __future__ import annotations
import sys, json, pathlib, datetime
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "antenna"))
import _style as S; S.use_light()

rows = json.load(open("/tmp/soak.json"))
ts = [datetime.datetime.fromisoformat(r["time"]) for r in rows]
t0 = ts[0]
h = np.array([(t - t0).total_seconds() / 3600 for t in ts])
vstor = np.array([r["battery_voltage"] for r in rows])
solar = np.array([r["solar_voltage"] for r in rows])

# relay s_relay snapshots taken during the run (elapsed h, forwarded, received)
snap_h   = np.array([0.0, 2.4, 7.6, 18.31])
snap_fwd = np.array([0,   176, 549, 1412])
snap_rx  = np.array([0,   243, 822, 2215])

fig, (axA, axB) = plt.subplots(1, 2, figsize=(13, 5))

# ---- A: TTN supply + solar over the soak ----
axA.plot(h, vstor, "-o", color=S.TEAL7, ms=3, lw=1.6, label="VSTOR (supply)")
axA.set_ylim(3.2, 5.0); axA.set_ylabel("VSTOR (V)", color=S.TEAL7)
axA.axhline(3.32, color=S.WARM, ls="--", lw=1.2)
axA.text(0.3, 3.38, "brownout 3.32 V (never approached)", color=S.WARM, fontsize=9)
axA.set_xlabel("hours into soak"); axA.set_title("A · TTN supply + solar over 18.3 h")
axA.tick_params(axis="y", labelcolor=S.TEAL7)
axS = axA.twinx()
axS.plot(h, solar, "-", color=S.WARM, lw=1.4, alpha=0.85, label="solar")
axS.axhline(3.0, color=S.DIM, ls=":", lw=1.1)
axS.text(h[-1], 3.05, "3.0 V flight relay gate", color=S.DIM, fontsize=8.5, ha="right")
axS.set_ylim(0, 5.0); axS.set_ylabel("solar (V)", color=S.WARM)
axS.tick_params(axis="y", labelcolor=S.WARM)
axA.text(0.02, 0.04, f"{len(rows)} uplinks · 95% delivered · VSTOR {vstor.min():.2f}-{vstor.max():.2f} V",
         transform=axA.transAxes, fontsize=9, color=S.TEXT)

# ---- B: relay cumulative forwarding ----
axB.plot(snap_h, snap_rx, "-o", color=S.DIM, ms=6, lw=1.6, label="received")
axB.plot(snap_h, snap_fwd, "-o", color=S.TEAL7, ms=6, lw=2.0, label="forwarded")
for x, y in zip(snap_h[1:], snap_fwd[1:]):
    axB.annotate(f"{y}", (x, y), textcoords="offset points", xytext=(0, 8), ha="center",
                 fontsize=9, color=S.TEAL7, fontweight="bold")
rate = snap_fwd[-1] / snap_h[-1]
axB.plot([0, 18.31], [0, rate * 18.31], ls=":", color=S.MINT, lw=1.2)
axB.set_xlabel("hours into soak"); axB.set_ylabel("cumulative Meshtastic frames")
axB.set_title(f"B · Relay forwarding (~{rate:.0f} frames/hr, exact accounting)")
axB.legend(loc="upper left", fontsize=9)
axB.text(0.02, 0.78, "2215 rx = 1412 fwd + 696 hop0\n+ 102 dedup + 5 cap-skip",
         transform=axB.transAxes, fontsize=9, color=S.TEXT)

fig.suptitle("Phase-2 soak: TTN telemetry stable, Meshtastic relay steady, one radio, 18.3 h",
             fontsize=13, fontweight="bold")
S.footer(fig, "soak_results.py · stratolink-2 · env:stratolink_soak (PSU 4.8V + solar) · 2026-06-03/04", light=True)
fig.tight_layout(rect=(0, 0.02, 1, 0.96))
fig.savefig(HERE / "soak_results.png", dpi=150)
print("wrote", HERE / "soak_results.png")
