#!/usr/bin/env python3
"""How Meshtastic 'managed flooding' interacts with a BALLOON node, the schematic
that explains why a naive high node preempts the whole region, and why ROUTER_LATE
flips it into a self-targeting gap-filler.

Managed flooding: on receiving a packet, a node waits a contention-window (CW)
delay, then rebroadcasts, UNLESS it hears someone else rebroadcast first, in which
case it cancels. The CW is SNR-BASED: a node that heard the packet WEAKLY (low SNR =
far away) gets a SHORTER delay and goes FIRST (so the farthest node extends range and
nearer nodes suppress). A balloon hears EVERYONE weakly (it's 400 km from all of
them), so the SNR rule tells it to go FIRST for almost every packet, and its 400 km
rebroadcast then suppresses local ground rebroadcasts region-wide. That is the precise
'ROUTER killed our mesh' mechanism. ROUTER_LATE overrides the SNR rule and forces the
balloon to a LATE window: it goes last, hears the ground nodes, and cancels where they
already covered it (dense) or fills the gap where nobody did (sparse).

Run: analysis/.venv/bin/python analysis/network/92_managed_flooding.py
"""
from __future__ import annotations
import pathlib
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "antenna"))
import _style as S
S.use_light()
FIGS = HERE / "figs"


def timeline(ax, title, nodes, late_balloon):
    """nodes: list of (label, delay, snr_txt, color, outcome) where outcome in
    {'tx','cancel','fill'}; delay on 0..1 contention window."""
    ax.set_xlim(-0.05, 1.18); ax.set_ylim(-0.5, len(nodes) - 0.5)
    ax.axvspan(0, 1.0, color=S.TEAL7, alpha=0.06)
    ax.axvline(1.0, color=S.TEXT_DIM, ls=":", lw=1)
    ax.text(0.5, len(nodes)-0.35, "← contention window (SNR-ordered) →", ha="center",
            fontsize=8.5, color=S.TEXT_DIM)
    for i, (lbl, d, snr, col, outcome) in enumerate(nodes):
        y = len(nodes) - 1 - i
        ax.plot([0, d], [y, y], "-", color=S.GRID, lw=1)
        mk = {"tx": "o", "cancel": "x", "fill": "*"}[outcome]
        ms = {"tx": 11, "cancel": 12, "fill": 16}[outcome]
        ax.plot(d, y, mk, color=col, ms=ms, mew=2.2, zorder=5)
        ax.text(-0.04, y, lbl, ha="right", va="center", fontsize=9, color=col, fontweight="bold")
        ax.text(d + 0.03, y, {"tx": "rebroadcasts", "cancel": "hears it already → CANCELS",
                              "fill": "nobody did → FILLS gap"}[outcome] + f"   ({snr})",
                va="center", fontsize=8.2, color=S.TEXT if outcome != "cancel" else S.TEXT_DIM)
    ax.set_yticks([]); ax.set_xticks([])
    ax.set_title(title, fontsize=11, loc="left")


def main():
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11.5, 7.2))
    # Panel A: default CLIENT/ROUTER, balloon's low SNR puts it FIRST -> preempts
    nodesA = [
        ("BALLOON", 0.08, "SNR -18 dB, hears all weakly", S.RED, "tx"),
        ("far ground node", 0.30, "SNR -8 dB", S.TEAL10, "cancel"),
        ("mid ground node", 0.58, "SNR 0 dB", S.TEAL10, "cancel"),
        ("near ground node", 0.85, "SNR +8 dB", S.TEAL10, "cancel"),
    ]
    timeline(ax1, "A · Default (CLIENT/ROUTER): the SNR rule makes the balloon go FIRST → "
             "its 400 km rebroadcast preempts the whole region", nodesA, False)
    ax1.text(0.08, -0.42, "balloon TX heard everywhere → every ground node cancels its own hop "
             "= 'ROUTER killed our mesh'", fontsize=8.3, color=S.RED, ha="left")

    # Panel B: ROUTER_LATE, balloon forced LAST -> defers (dense) / fills (sparse)
    nodesB = [
        ("near ground node", 0.22, "SNR +8 dB", S.TEAL10, "tx"),
        ("mid ground node", 0.45, "SNR 0 dB", S.TEAL10, "cancel"),
        ("BALLOON (dense area)", 1.10, "forced to LATE window", S.MINT, "cancel"),
        ("BALLOON (sparse area)", 1.10, "forced to LATE window", S.L_ACCENT, "fill"),
    ]
    timeline(ax2, "B · ROUTER_LATE: balloon forced to the LATE window → ground goes first; "
             "balloon cancels where covered, fills where sparse", nodesB, True)
    ax2.text(1.10, -0.42, "= the self-targeting from N9, for free: silent over dense mesh, "
             "carries the traffic where nobody else can", fontsize=8.3, color=S.L_ACCENT, ha="right")

    fig.suptitle("Managed flooding + a balloon: the SNR contention window is the trap; "
                 "ROUTER_LATE is the flip", fontsize=12.5)
    S.footer(fig, "92_managed_flooding.py · schematic of Meshtastic managed-flood contention window vs a wide/high node", light=True)
    fig.tight_layout(rect=(0, 0.01, 1, 0.97))
    fig.savefig(FIGS / "N10_managed_flooding.png", dpi=145); plt.close(fig)
    print("wrote N10_managed_flooding.png")


if __name__ == "__main__":
    main()
