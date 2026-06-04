#!/usr/bin/env python3
"""Schematic of cooperative SX1262 time-sharing: LoRaWAN (priority, scheduled) +
a Meshtastic-compatible repeater borrowing the radio in the FULL+sun idle gap.

One ~1200 s cycle. TTN owns the radio on its fixed cadence; the repeater fills the
sleep time IF power allows, and yields the radio back before the next TTN slot.
Numbers from our firmware + the integration research (RadioLib reconfig ~1 ms;
LongFast SF11/BW250/sync0x2B/pre16/906.875|869.525 MHz; RX ~5.5 mA; STOP1 ~4 µA).

Run: analysis/.venv/bin/python analysis/network/93_radio_sharing.py
"""
from __future__ import annotations
import pathlib
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "antenna"))
import _style as S
S.use_light()
FIGS = HERE / "figs"

# phase: (name, width, color, radio_cfg, activity, power)
PH = [
    ("GPS fix\n≤30 s", 26, S.DIM, "LoRaWAN profile", "u-blox acquire", "~30 mA"),
    ("TX uplink\n0.31 s", 7, S.TEAL10, "SF9 / BW125\nsync 0x34", "LoRaWAN uplink", "44 mA"),
    ("swap\n~1 ms", 5, S.WARM, "standby →\nset SF/BW/sync/\nfreq/preamble", "reconfig radio", "-"),
    ("MESHTASTIC RELAY  (gated: tier FULL + sun, up to ~19 min)", 46, S.TEAL7,
     "SF11 / BW250\nsync 0x2B / pre16\n906.875 | 869.525 MHz", "RX-listen +\nROUTER_LATE forward\n(MCU STOP2, wake on RxDone)", "~5.5 mA\nfloor-abort <4.7 V"),
    ("swap", 5, S.WARM, "→ LoRaWAN\nprofile", "yields radio\n~2 s before TTN", "-"),
    ("SLEEP\nremainder / night", 22, S.MINT, "SX1262 SLEEP", "MCU STOP1", "~4 µA"),
]


def main():
    fig, ax = plt.subplots(figsize=(13.5, 5.6))
    x = 0
    for name, w, col, cfg, act, pwr in PH:
        ax.add_patch(FancyBboxPatch((x, 3.0), w, 1.25, boxstyle="round,pad=0.1",
                                    fc=col, ec=S.TEXT, alpha=0.22, lw=1.2))
        ax.text(x + w/2, 3.62, name, ha="center", va="center", fontsize=8.7, fontweight="bold", color=S.TEXT)
        ax.text(x + w/2, 2.55, cfg, ha="center", va="top", fontsize=7.6, color=S.L_ACCENT)
        ax.text(x + w/2, 1.55, act, ha="center", va="top", fontsize=7.6, color=S.TEXT)
        ax.text(x + w/2, 0.62, pwr, ha="center", va="top", fontsize=8, color=S.RED, fontweight="bold")
        x += w + 1.5
    total = x
    # lane labels
    for y, lbl in ((3.62, "phase"), (2.45, "radio config"), (1.45, "activity"), (0.5, "power")):
        ax.text(-1.5, y, lbl, ha="right", va="center", fontsize=8, color=S.TEXT_DIM, style="italic")
    # priority brackets
    ax.annotate("", (33, 4.55), (0, 4.55), arrowprops=dict(arrowstyle="-", color=S.TEAL10, lw=2))
    ax.text(16.5, 4.7, "TTN cycle, PRIORITY, fixed cadence (owns the radio)", ha="center", fontsize=9, color=S.TEAL10, fontweight="bold")
    ax.annotate("", (96, 4.55), (40, 4.55), arrowprops=dict(arrowstyle="-", color=S.L_ACCENT, lw=2))
    ax.text(68, 4.7, "borrowed idle time, relay only if power allows", ha="center", fontsize=9, color=S.L_ACCENT, fontweight="bold")
    ax.text(total/2, -0.2, "Integration point = ONE line in main.cpp loop(): the end-of-cycle "
            "power_manager_sleep_ms() becomes \"relay-then-sleep\" when tier==FULL && solar."
            "   Single SX1262, no second radio.",
            ha="center", fontsize=8.6, color=S.TEXT, style="italic")
    ax.set_xlim(-9, total + 1); ax.set_ylim(-0.6, 5.1); ax.axis("off")
    ax.set_title("Cooperative SX1262 sharing: LoRaWAN (priority) + Meshtastic repeater in the FULL+sun gaps",
                 fontsize=12.3, fontweight="bold")
    S.footer(fig, "93_radio_sharing.py · one ~1200 s cycle (widths schematic, durations labeled) · params from firmware + integration research", light=True)
    fig.tight_layout()
    fig.savefig(FIGS / "N11_radio_sharing.png", dpi=145); plt.close(fig)
    print("wrote N11_radio_sharing.png")


if __name__ == "__main__":
    main()
