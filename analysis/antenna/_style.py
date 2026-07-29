"""Shared plot styling for the antenna analysis — matches the Stratolink
dashboard-v2 look (deep navy field, teal accents) so these figures read as
part of the same family.

Palette lifted from web/components/maps/* (origin/main):
  bg        rgb(8,13,23)      #080d17   page field
  panel     rgb(13,20,34)     #0d1422   slightly lifted card
  teal      #6fe0c8 / #4fc8b4 / #3fb8a0  SF7 / SF10 / SF12 rings
  mint      #5eead4           primary accent (rgba 94,234,212)
  dim       #4a6b66           out-of-range / muted
  text      rgb(200,212,232)  #c8d4e8
"""
from __future__ import annotations
import matplotlib as mpl
import matplotlib.pyplot as plt

BG     = "#080d17"
PANEL  = "#0d1422"
TEAL7  = "#6fe0c8"   # SF7 — the range we actually fly
TEAL10 = "#4fc8b4"
TEAL12 = "#3fb8a0"
MINT   = "#5eead4"
DIM    = "#4a6b66"
TEXT   = "#c8d4e8"
TEXT_DIM = "#7e8aa3"
WARM   = "#f4a259"   # warm accent for "bad"/floor markers
RED    = "#e0594a"   # stale / contamination
GRID   = "#1c2740"

# RSSI colormap: turbo reads well on dark and spans the floor→strong range.
RSSI_CMAP = "turbo"
RSSI_VMIN, RSSI_VMAX = -130, -95   # dBm; floor ~ -129, strong flight ~ -98

# SF7/BW125 demod floor (from analysis/research/lora.md): -174+10log10(125e3)+NF(6)+SNRlim(-7.5)
SF7_SENS_DBM = -124.5


def use_dark():
    """Apply the dashboard dark theme to matplotlib rcParams."""
    plt.rcParams.update({
        "figure.facecolor": BG,
        "savefig.facecolor": BG,
        "axes.facecolor": PANEL,
        "axes.edgecolor": GRID,
        "axes.labelcolor": TEXT,
        "axes.titlecolor": TEXT,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.alpha": 0.7,
        "grid.linewidth": 0.6,
        "text.color": TEXT,
        "xtick.color": TEXT_DIM,
        "ytick.color": TEXT_DIM,
        "legend.facecolor": PANEL,
        "legend.edgecolor": GRID,
        "legend.framealpha": 0.92,
        "font.size": 11,
        "axes.titlesize": 13,
        "axes.titleweight": "bold",
        "figure.titlesize": 15,
        "figure.titleweight": "bold",
    })


def footer(fig, text, light=False):
    """Small provenance line bottom-left — keeps figures self-describing."""
    fig.text(0.008, 0.005, text, fontsize=7.5,
             color=(L_TEXT_DIM if light else TEXT_DIM), ha="left", va="bottom")


# --- Light theme (4nec2 / NEC-tool aesthetic — Teddy's preferred style) -------
L_BG    = "#ffffff"
L_PANEL = "#f4f6f8"
L_TEXT  = "#1a2230"
L_TEXT_DIM = "#5b6675"
L_GRID  = "#c9d2dd"
L_ACCENT = "#0a7d6b"   # teal that reads on white
PAT_CMAP = "turbo"      # rainbow doughnut like the 4nec2 3D viewer

# distinct, print-legible series colors on white
L_SERIES = {
    "monopole+PCB":      "#d11149",   # crimson
    "monopole as-flown": "#d11149",
    "vertical dipole":   "#1a8fe3",   # blue
    "horizontal dipole": "#f17105",   # orange
    "turnstile":         "#6a4c93",   # purple
    "as-flown +panels":  "#0a9396",   # teal
}


def use_light():
    """Apply a clean light theme matching the 4nec2 look Teddy prefers.

    Also REBINDS the shared color-name globals (BG, PANEL, TEAL7, MINT, ...) to
    light-legible equivalents so existing plot code that references S.TEAL7 etc.
    automatically renders correctly on white — no per-script edits needed."""
    global BG, PANEL, TEAL7, TEAL10, TEAL12, MINT, DIM, TEXT, TEXT_DIM, WARM, RED, GRID
    BG, PANEL = L_BG, L_PANEL
    TEXT, TEXT_DIM, GRID = L_TEXT, L_TEXT_DIM, L_GRID
    # series colors chosen to read on white (the dark teals vanish on white)
    TEAL7  = "#0a9396"   # primary series / "good" antenna
    TEAL10 = "#1a8fe3"   # secondary (blue)
    TEAL12 = "#118a7e"   # tertiary
    MINT   = "#0a7d6b"   # accent / annotation
    DIM    = "#9aa6b4"   # muted / out-of-range
    WARM   = "#f17105"   # warm "bad"/floor marker
    RED    = "#d11149"   # stale / contamination
    plt.rcParams.update({
        "figure.facecolor": L_BG,
        "savefig.facecolor": L_BG,
        "axes.facecolor": L_BG,
        "axes.edgecolor": L_TEXT_DIM,
        "axes.labelcolor": L_TEXT,
        "axes.titlecolor": L_TEXT,
        "axes.grid": True,
        "grid.color": L_GRID,
        "grid.alpha": 1.0,
        "grid.linewidth": 0.6,
        "text.color": L_TEXT,
        "xtick.color": L_TEXT,
        "ytick.color": L_TEXT,
        "legend.facecolor": L_PANEL,
        "legend.edgecolor": L_GRID,
        "legend.framealpha": 0.95,
        "font.size": 11,
        "axes.titlesize": 13,
        "axes.titleweight": "bold",
        "figure.titlesize": 15,
        "figure.titleweight": "bold",
    })
