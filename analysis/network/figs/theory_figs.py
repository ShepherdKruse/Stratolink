#!/usr/bin/env python3
"""Four Stratolink 'theory / what we found' graphics, minimal line-art aesthetic:
monochrome ink on white, serif labels, lots of air, no em dashes.

  fig_acoustic   the 'acoustic' events were the harvester's self-noise (follow the sun)
  fig_sf9        SF7 -> SF9 buys ~2x reach, the biggest lever, zero hardware
  fig_oneradio   one radio, two networks: TTN telemetry is 0.026% of the time
  fig_oceangap   TTN is only as dense as its ground gateways; the ocean has none
"""
from __future__ import annotations
import pathlib, numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse, Arc, Rectangle

OUT = pathlib.Path(__file__).resolve().parent
INK, MID, FAINT = "#1a1a1a", "#777777", "#b9b9b9"
plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Latin Modern Roman", "CMU Serif", "Georgia", "DejaVu Serif"],
    "mathtext.fontset": "cm",
    "figure.facecolor": "white", "savefig.facecolor": "white", "axes.facecolor": "white",
})


def titleblock(fig, title, *lines, x=0.06, y=0.93):
    fig.text(x, y, "   ".join(title.upper()), fontsize=15, color=INK)
    for i, ln in enumerate(lines):
        fig.text(x, y - 0.052 - i * 0.038, ln, fontsize=11.3, color="#333333")


def footer(fig, txt):
    fig.text(0.97, 0.02, txt, ha="right", color=MID, fontsize=8, style="italic")


# ------------------------------------------------------------ A: acoustic / harvester
def fig_acoustic():
    fig, ax = plt.subplots(figsize=(11, 4.8))
    fig.subplots_adjust(left=0.05, right=0.97, top=0.78, bottom=0.12)
    ax.set_xlim(0, 24); ax.set_ylim(0, 1); ax.axis("off")
    # night bands
    for a, b in [(0, 6.2), (18.2, 24)]:
        ax.add_patch(Rectangle((a, 0), b - a, 1, color=INK, alpha=0.045, lw=0))
    # ground + sun arc
    ax.plot([0, 24], [0.16, 0.16], color=INK, lw=1.1)
    t = np.linspace(6.2, 18.2, 120)
    ax.plot(t, 0.16 + 0.52 * np.sin((t - 6.2) / 12 * np.pi), color=INK, lw=1.0)
    ax.plot([12], [0.68], marker="o", ms=8, mfc="white", mec=INK, mew=1.2)   # sun
    # 'acoustic' event ticks: heavily clustered in daylight
    rng = np.random.default_rng(3)
    day = np.sort(rng.uniform(6.6, 17.8, 22)); night = np.sort(rng.uniform(0.5, 5.6, 4))
    night = np.append(night, rng.uniform(18.6, 23.5, 1))
    for e in day:
        ax.plot([e, e], [0.16, 0.16 + 0.075], color=INK, lw=1.3)
    for e in night:
        ax.plot([e, e], [0.16, 0.16 + 0.045], color=MID, lw=1.0)
    ax.text(12, 0.045, "79% of 'acoustic' events fall in daylight", ha="center", color=INK, fontsize=11)
    ax.text(3.1, 0.045, "18% at night", ha="center", color=MID, fontsize=9.5)
    ax.text(21, 0.045, "", ha="center")
    for h, lab in [(0, "midnight"), (6, "dawn"), (12, "noon"), (18, "dusk"), (24, "midnight")]:
        ax.text(h, 0.135, lab, ha="center", va="top", color=MID, fontsize=8.5)
    titleblock(fig, "the acoustic events followed the sun",
               "Telemetry kept flagging 'acoustic events'. They tracked daylight and the energy",
               "harvester's load, not sound: 0.4% on the bench vs 50% in flight. It was the",
               "harvester's own electrical self-noise, mistaken for the microphone.")
    footer(fig, "stratolink-3 flight telemetry, day/night split")
    fig.savefig(OUT / "theory_acoustic.png", dpi=165); plt.close(fig)
    print("wrote", OUT / "theory_acoustic.png")


# ------------------------------------------------------------ B: SF9 reach
def _balloon(ax, bx, by, r=0.9):
    ax.add_patch(Ellipse((bx, by), 0.52 * r, 0.66 * r, fill=False, ec=INK, lw=1.3))
    ax.plot([bx, bx], [by - 0.33 * r, by - 0.62 * r], color=INK, lw=0.8)
    ax.add_patch(Rectangle((bx - 0.07 * r, by - 0.74 * r), 0.14 * r, 0.12 * r, fill=False, ec=INK, lw=1.1))
    return (bx, by - 0.74 * r)


def fig_sf9():
    fig, ax = plt.subplots(figsize=(10, 6.2))
    fig.subplots_adjust(left=0.04, right=0.96, top=0.80, bottom=0.04)
    ax.set_xlim(-6, 6); ax.set_ylim(-0.4, 6.2); ax.set_aspect("equal"); ax.axis("off")
    ax.plot([-6, 6], [0.0, 0.0], color=INK, lw=1.2)                 # ground
    apex = _balloon(ax, 0, 5.2, r=1.0)
    r7, r9 = 2.4, 4.3                                              # SF7 vs SF9 ground reach (~1.8x)
    for r, lab, ls, col in [(r7, "SF7  (flown)", (0, (5, 3)), MID), (r9, "SF9  (next flight)", "-", INK)]:
        th = np.linspace(0, np.pi, 120)
        ax.plot(r * np.cos(th), r * np.sin(th) * 0.16, color=col, lw=1.3, ls=ls)   # reach arc on ground
        ax.plot([apex[0], r], [apex[1], 0], color=col, lw=0.8, ls=ls)
        ax.plot([apex[0], -r], [apex[1], 0], color=col, lw=0.8, ls=ls)
        ax.text(r, 0.16 * 0 + 0.16, lab, ha="left", va="bottom", color=col, fontsize=10.5,
                rotation=0)
    ax.annotate("", xy=(r7, 0.0), xytext=(r9, 0.0), arrowprops=dict(arrowstyle="<->", color=INK, lw=1.0))
    ax.text((r7 + r9) / 2, -0.28, "+5 dB  ~2x range", ha="center", va="top", color=INK, fontsize=11)
    titleblock(fig, "one setting, twice the reach",
               "Flight 3 ran at the SF7 sensitivity floor. Moving uplinks to SF9 buys about +5 dB,",
               "roughly double the link range, comfortably past the ~412 km radio horizon at 12 km.",
               "The single biggest lever for the next flight, and it costs zero extra hardware.")
    footer(fig, "LoRa link budget, SF7 vs SF9")
    fig.savefig(OUT / "theory_sf9_reach.png", dpi=165); plt.close(fig)
    print("wrote", OUT / "theory_sf9_reach.png")


# ------------------------------------------------------------ C: one radio, two networks
def fig_oneradio():
    fig, ax = plt.subplots(figsize=(11, 3.3))
    fig.subplots_adjust(left=0.05, right=0.97, top=0.62, bottom=0.10)
    ax.set_xlim(0, 100); ax.set_ylim(0, 1); ax.axis("off")
    # the radio's time as one long bar
    ax.add_patch(Rectangle((0, 0.40), 100, 0.34, fill=True, fc=INK, alpha=0.06, ec=INK, lw=1.1))
    # TTN sliver (0.026% is invisible; draw a thin mark and label true value)
    ax.add_patch(Rectangle((0, 0.40), 0.6, 0.34, fill=True, fc=INK, lw=0))
    ax.annotate("TTN telemetry: 308 ms every 20 min  =  22 s/day  (0.026%)",
                xy=(0.6, 0.74), xytext=(6, 1.02), fontsize=11, color=INK,
                arrowprops=dict(arrowstyle="->", color=INK, lw=0.9), va="center")
    ax.text(50, 0.61, "free for a Meshtastic relay  ~  99.97% of the radio's time",
            ha="center", va="center", color=INK, fontsize=12.5)
    ax.text(50, 0.25, "(the relay only runs on surplus power, and yields instantly to every uplink)",
            ha="center", va="top", color=MID, fontsize=9.5, style="italic")
    titleblock(fig, "one radio, two networks",
               "Telemetry to The Things Network barely touches the radio. The rest of the time the",
               "one flight radio is idle, so at full power it relays the local Meshtastic mesh for free.",
               x=0.05, y=0.93)
    footer(fig, "SF9, 35 byte uplink, 1200 s cadence")
    fig.savefig(OUT / "theory_one_radio.png", dpi=165); plt.close(fig)
    print("wrote", OUT / "theory_one_radio.png")


# ------------------------------------------------------------ D: ocean gap
def fig_oceangap():
    fig, ax = plt.subplots(figsize=(11, 5.0))
    fig.subplots_adjust(left=0.05, right=0.97, top=0.78, bottom=0.10)
    ax.set_xlim(0, 100); ax.set_ylim(0, 1); ax.axis("off")
    yp = 0.62
    ax.plot([4, 96], [yp, yp], color=INK, lw=1.2)                  # flight path
    # waypoints
    for x, lab in [(8, "San Francisco"), (30, "US east coast"), (72, "Iberia"), (92, "Spain")]:
        ax.plot([x], [yp], marker="o", ms=4.5, color=INK)
        ax.text(x, yp + 0.05, lab, ha="center", va="bottom", color=INK, fontsize=9.5)
    # ocean gap
    ax.add_patch(Rectangle((33, 0.20), 36, 0.62, color=INK, alpha=0.04, lw=0))
    ax.annotate("", xy=(33, 0.30), xytext=(69, 0.30), arrowprops=dict(arrowstyle="<->", color=MID, lw=0.9))
    ax.text(51, 0.245, "Atlantic crossing:  ~8 days, zero gateways", ha="center", va="top",
            color=INK, fontsize=11)
    # gateway 'density' ticks below the path: thin CONUS, dense Iberia, none over ocean
    rng = np.random.default_rng(11)
    conus = rng.uniform(6, 32, 7); iberia = rng.uniform(66, 94, 26)
    for g in conus: ax.plot([g, g], [yp - 0.02, yp - 0.09], color=MID, lw=0.9)
    for g in iberia: ax.plot([g, g], [yp - 0.02, yp - 0.11], color=INK, lw=0.9)
    ax.text(19, yp - 0.16, "CONUS: thin, 60% of\nuplinks heard by one gateway", ha="center",
            va="top", color=MID, fontsize=8.8)
    ax.text(80, yp - 0.16, "Iberia: ~140 gateways\nnearby, dense", ha="center", va="top",
            color=INK, fontsize=8.8)
    titleblock(fig, "the ocean has no gateways",
               "The Things Network is only as dense as its ground gateways. Iberia is thick with them,",
               "the US is thin, and the open Atlantic has none, so flight 3 went ~8 days dark over water.",
               "That ocean gap is exactly what a drifting relay constellation is there to fill.")
    footer(fig, "stratolink-3 path, TTN gateway geography")
    fig.savefig(OUT / "theory_ocean_gap.png", dpi=165); plt.close(fig)
    print("wrote", OUT / "theory_ocean_gap.png")


if __name__ == "__main__":
    fig_acoustic(); fig_sf9(); fig_oneradio(); fig_oceangap()
