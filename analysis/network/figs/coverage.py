#!/usr/bin/env python3
"""Stratolink coverage schematics, minimal line-art / plotter aesthetic:
monochrome strokes on white, serif labels, faint construction arcs, lots of air.
Rainbow is used ONLY to distinguish multiple balloons.

Produces static PNGs and looping GIFs (frames -> imagemagick).
  python coverage.py            # statics only
  python coverage.py --gif      # statics + GIFs
"""
from __future__ import annotations
import sys, pathlib, shutil, subprocess, tempfile
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse

OUT = pathlib.Path(__file__).resolve().parent; OUT.mkdir(parents=True, exist_ok=True)

INK   = "#1a1a1a"      # primary stroke
FAINT = "#b9b9b9"      # construction arcs
MID   = "#777777"      # secondary / dimension lines
plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Latin Modern Roman", "CMU Serif", "Georgia", "DejaVu Serif"],
    "mathtext.fontset": "cm",
    "figure.facecolor": "white", "savefig.facecolor": "white", "axes.facecolor": "white",
})

W, H = 1000.0, 660.0
SX   = W * 0.5
ALT  = 430.0
HALF = 300.0
RC   = 2600.0
GY   = 150.0
DRIFT = 120.0          # single-balloon sway amplitude (keeps footprint + labels on-canvas)


def ground(x):
    return GY - (x - SX) ** 2 / (2 * RC)


def draw_balloon(ax, bx, by, color=INK, scale=1.0, label=None):
    rw, rh = 26 * scale, 32 * scale
    ax.add_patch(Ellipse((bx, by), rw * 2, rh * 2, fill=False, ec=color, lw=1.4, zorder=6))
    ax.add_patch(plt.Polygon([(bx - 5 * scale, by - rh), (bx + 5 * scale, by - rh),
                              (bx, by - rh - 9 * scale)], closed=True, fill=False, ec=color, lw=1.1, zorder=6))
    sy = by - rh - 9 * scale
    ty = sy - 34 * scale
    ax.plot([bx, bx], [sy, ty], color=color, lw=0.9, zorder=6)
    bw, bh = 17 * scale, 11 * scale
    ax.add_patch(plt.Rectangle((bx - bw / 2, ty - bh), bw, bh, fill=False, ec=color, lw=1.2, zorder=7))
    ax.plot([bx, bx], [ty - bh, ty - bh - 16 * scale], color=color, lw=1.0, zorder=7)
    if label:
        ax.text(bx, by + rh + 16, label, ha="center", va="bottom", color=color, fontsize=10.5, style="italic")
    return (bx, ty - bh - 16 * scale)


def draw_single(ax, bx, swath=False):
    ax.set_xlim(0, W); ax.set_ylim(0, H); ax.set_aspect("equal"); ax.axis("off")
    gx = np.linspace(60, W - 60, 400)
    ax.plot(gx, ground(gx), color=INK, lw=1.3, zorder=4)

    if swath:   # faint corridor the balloon sweeps as it drifts
        cxl, cxr = SX - DRIFT - HALF, SX + DRIFT + HALF
        bxs = np.linspace(cxl, cxr, 120)
        ax.fill_between(bxs, ground(bxs), ground(bxs) + 6, color=INK, alpha=0.04, zorder=1)

    xl, xr = bx - HALF, bx + HALF
    yl, yr = ground(xl), ground(xr)
    sx, sy = bx, ground(bx)
    apex = draw_balloon(ax, bx, sy + ALT, label="stratolink", color=INK)

    for r in np.linspace(HALF / 5, HALF, 5):
        th = np.linspace(np.pi, 2 * np.pi, 100)
        ax.plot(sx + r * np.cos(th), sy - r * np.sin(th) * 0.30, color=FAINT, lw=0.7, zorder=2)

    ax.plot([apex[0], xl], [apex[1], yl], color=INK, lw=1.0, zorder=5)
    ax.plot([apex[0], xr], [apex[1], yr], color=INK, lw=1.0, zorder=5)
    ax.fill([apex[0], xl, xr], [apex[1], yl, yr], color=INK, alpha=0.05, zorder=3)

    ax.annotate("", xy=(sx, sy), xytext=(sx, apex[1]), arrowprops=dict(arrowstyle="<->", color=MID, lw=0.9))
    ax.text(sx - 14, (sy + apex[1]) / 2, r"$\approx 12\ \mathrm{km}$", rotation=90,
            ha="right", va="center", color=MID, fontsize=11)

    dimy = min(yl, yr) - 46
    ax.annotate("", xy=(xl, dimy), xytext=(xr, dimy), arrowprops=dict(arrowstyle="<->", color=INK, lw=1.0))
    ax.plot([xl, xl], [yl, dimy], color=MID, lw=0.6, ls=(0, (4, 3)))
    ax.plot([xr, xr], [yr, dimy], color=MID, lw=0.6, ls=(0, (4, 3)))
    ax.text(SX, GY - HALF / (2 * RC) * 0 - 102, r"$\approx 400\ \mathrm{km}$  of LoRa / Meshtastic coverage",
            ha="center", va="top", color=INK, fontsize=12)
    ax.text(SX, GY - 138, "open ocean · deep desert · out of reach of any tower",
            ha="center", va="top", color=MID, fontsize=10, style="italic")


def make_single_fig(bx, swath=False):
    fig, ax = plt.subplots(figsize=(10, 6.6))
    fig.subplots_adjust(left=0.04, right=0.96, top=0.84, bottom=0.04)
    for s in ax.spines.values(): s.set_visible(False)
    draw_single(ax, bx, swath=swath)
    fig.text(0.045, 0.945, "T R A N S I E N T   L O R A   C O V E R A G E", fontsize=15.5, color=INK)
    fig.text(0.045, 0.905, "A pico-balloon at float altitude relays LoRa / Meshtastic to everything beneath it.",
             fontsize=11.5, color="#333333")
    fig.text(0.045, 0.878, "One balloon, at full power, opens ~400 km of transient coverage where no tower reaches.",
             fontsize=11.5, color="#333333")
    fig.text(0.96, 0.018, "not to scale", ha="right", color=MID, fontsize=8.5, style="italic")
    return fig


# ---------------------------------------------------------------- multi (top-down)
RAINBOW = ["#d11149", "#f17105", "#d9a200", "#0a9396", "#1a8fe3", "#6a4c93"]
# clustered over one region so footprints overlap (the mesh) while the globe stays fully visible around them
BASE = [(-95, 70), (40, 105), (-130, -25), (35, -55), (120, 35), (-25, -110)]
DISC_R = 285.0
FP = 90.0


def draw_multi(ax, balloons):
    cx, cy = W / 2, H * 0.50
    ax.set_xlim(0, W); ax.set_ylim(0, H); ax.set_aspect("equal"); ax.axis("off")
    ax.add_patch(plt.Circle((cx, cy), DISC_R, fill=False, ec=MID, lw=1.2, zorder=2))
    ax.add_patch(Ellipse((cx, cy), DISC_R * 2, DISC_R * 0.66, fill=False, ec=FAINT, lw=0.6, zorder=1))
    ax.add_patch(Ellipse((cx, cy), DISC_R * 0.66, DISC_R * 2, fill=False, ec=FAINT, lw=0.6, zorder=1))
    clip = plt.Circle((cx, cy), DISC_R, transform=ax.transData)
    for (dx, dy), col in zip(balloons, RAINBOW):
        bx, by = cx + dx, cy + dy
        foot = ax.add_patch(plt.Circle((bx, by), FP, fill=True, fc=col, ec=col, lw=1.4, alpha=0.10, zorder=3))
        ring = ax.add_patch(plt.Circle((bx, by), FP, fill=False, ec=col, lw=1.4, zorder=4))
        foot.set_clip_path(clip); ring.set_clip_path(clip)
        ax.plot([bx], [by], marker="o", ms=4.0, color=col, zorder=6)
    ax.text(cx, cy - DISC_R - 18, "overlapping footprints hand off coverage as the balloons drift",
            ha="center", va="top", color=MID, fontsize=10.5, style="italic")


def make_multi_fig(balloons):
    fig, ax = plt.subplots(figsize=(8.6, 7.4))
    fig.subplots_adjust(left=0.04, right=0.96, top=0.86, bottom=0.05)
    for s in ax.spines.values(): s.set_visible(False)
    draw_multi(ax, balloons)
    fig.text(0.5, 0.95, "A   C O N S T E L L A T I O N   T I L E S   T H E   G A P", ha="center", fontsize=15.5, color=INK)
    fig.text(0.5, 0.905, "Cheap pico-balloons drift as a loose constellation; their ~400 km footprints overlap",
             ha="center", fontsize=11.5, color="#333333")
    fig.text(0.5, 0.882, "into rolling, decentralized LoRa coverage over oceans and remote interior.",
             ha="center", fontsize=11.5, color="#333333")
    fig.text(0.96, 0.015, "not to scale", ha="right", color=MID, fontsize=8.5, style="italic")
    return fig


def assemble_gif(frames_dir, pattern, out, delay=7):
    tool = shutil.which("magick") or shutil.which("convert")
    cmd = ([tool, "convert"] if tool and tool.endswith("magick") else [tool])
    subprocess.run(cmd + ["-delay", str(delay), "-loop", "0",
                          str(frames_dir / pattern), "-layers", "Optimize", str(out)], check=True)
    print("wrote", out)


# ---------------------------------------------------------------- render
fig = make_single_fig(SX, swath=False); fig.savefig(OUT / "coverage_single_static.png", dpi=170); plt.close(fig)
print("wrote", OUT / "coverage_single_static.png")
fig = make_multi_fig(BASE); fig.savefig(OUT / "coverage_multi_static.png", dpi=170); plt.close(fig)
print("wrote", OUT / "coverage_multi_static.png")

if "--gif" in sys.argv:
    N = 44
    # single: gentle ping-pong sway (seamless loop), swath corridor visible
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        phase = np.concatenate([np.linspace(0, 1, N // 2), np.linspace(1, 0, N // 2)])
        for i, p in enumerate(phase):
            bx = SX + DRIFT * (2 * p - 1)
            fg = make_single_fig(bx, swath=True); fg.savefig(td / f"s{i:03d}.png", dpi=105); plt.close(fg)
        assemble_gif(td, "s*.png", OUT / "coverage_single.gif", delay=7)
    # multi: each balloon on a slow circular orbit (seamless loop), footprints sliding
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        rng = np.random.default_rng(7)
        rad = rng.uniform(12, 22, len(BASE)); ph0 = rng.uniform(0, 2 * np.pi, len(BASE))
        for i in range(N):
            t = 2 * np.pi * i / N
            balloons = [(dx + r * np.cos(t + p), dy + r * np.sin(t + p))
                        for (dx, dy), r, p in zip(BASE, rad, ph0)]
            fg = make_multi_fig(balloons); fg.savefig(td / f"m{i:03d}.png", dpi=105); plt.close(fg)
        assemble_gif(td, "m*.png", OUT / "coverage_multi.gif", delay=7)
