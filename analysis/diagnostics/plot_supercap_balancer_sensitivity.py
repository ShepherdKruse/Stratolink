#!/usr/bin/env python3
"""Visualize divider safety, runtime, and balancer-correction sensitivity."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "analysis/antenna"))
import _style as S

from supercap_balance_audit import architecture_sensitivity


OPTIONS_MOHM = (7.50, 7.32, 7.15)
LABELS = ("7.50 reference", "7.32 safer-margin", "7.15 ratio option")


def main() -> None:
    import matplotlib.pyplot as plt
    import numpy as np

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=(
            ROOT
            / "analysis/visualization/stratolink2_supercap_balancer_sensitivity.png"
        ),
    )
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite evidence: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(
        f".{args.output.stem}.partial{args.output.suffix}"
    )
    if temporary.exists():
        raise SystemExit(f"refusing to overwrite partial evidence: {temporary}")

    rows = [architecture_sensitivity(value) for value in OPTIONS_MOHM]
    x = np.arange(len(rows))
    cell_margin_mv = np.array(
        [float(row["worst_initial_cell_margin_to_2v75_v"]) * 1000 for row in rows]
    )
    tlv_demand_ma = np.array(
        [
            float(row["tlv8801"]["initial_4pct_mismatch_correction_demand_ma"])
            for row in rows
        ]
    )
    ald_equalization_ua = np.array(
        [
            float(row["ald910025_typical_only"]["initial_net_equalizing_current_ua"])
            for row in rows
        ]
    )
    tlv_runtime_h = np.array(
        [float(row["tlv8801"]["minimum_cap_screening_runtime_h"]) for row in rows]
    )
    ald_runtime_h = np.array(
        [
            float(
                row["ald910025_typical_only"][
                    "minimum_cap_25c_runtime_h_with_min_25c_threshold"
                ]
            )
            for row in rows
        ]
    )

    S.use_light()
    fig, axes = plt.subplots(2, 2, figsize=(13.5, 9.0), sharex=True)
    fig.subplots_adjust(left=0.085, right=0.975, top=0.88, bottom=0.16,
                        hspace=0.34, wspace=0.25)
    fig.suptitle(
        "StratoLink-2 divider / balancer sensitivity · source-screen boundaries"
    )
    colors = [S.WARM, S.TEAL7, S.TEAL10]

    panels = axes.ravel()
    panels[0].bar(x, cell_margin_mv, color=colors, alpha=0.88)
    panels[0].axhline(0, color=S.L_TEXT, lw=1.0)
    panels[0].set_ylabel("Worst initial cell margin (mV)")
    panels[0].set_title("±4% cell-match screen")

    panels[1].plot(x, tlv_demand_ma, marker="o", color=S.WARM, lw=2.0)
    panels[1].axhline(4.7, color=S.RED, lw=1.2, ls="--",
                      label="TI 4.7 mA typical only")
    panels[1].set_ylabel("TLV initial demand (mA)")
    panels[1].set_title("TLV8801 correction authority")
    panels[1].legend(frameon=False, fontsize=9)

    panels[2].plot(x, ald_equalization_ua, marker="o", color=S.TEAL10, lw=2.0)
    panels[2].set_ylabel("ALD net equalization (µA)")
    panels[2].set_title("ALD910025 initial response · typical curve")

    panels[3].plot(x, tlv_runtime_h, marker="o", color=S.WARM, lw=2.0,
                   label="TLV max-IQ model")
    panels[3].plot(x, ald_runtime_h, marker="s", color=S.TEAL10, lw=2.0,
                   label="ALD 25 °C typical model")
    panels[3].set_ylabel("0.8 F baseline darkness (h)")
    panels[3].set_title("Reserve before active cycles / cold")
    panels[3].legend(frameon=False, fontsize=9)

    for ax in panels:
        ax.set_xticks(x, LABELS, rotation=8, ha="right")
        ax.grid(axis="x", visible=False)
    for ax, values, suffix, decimals in (
        (panels[0], cell_margin_mv, " mV", 0),
        (panels[1], tlv_demand_ma, " mA", 3),
        (panels[2], ald_equalization_ua, " µA", 1),
    ):
        for index, value in enumerate(values):
            ax.annotate(
                f"{value:.{decimals}f}{suffix}",
                (index, value),
                xytext=(0, 7),
                textcoords="offset points",
                ha="center",
                fontsize=9,
            )

    S.footer(
        fig,
        "BQ25570 ±2% + 1% divider/TCR screen · CAP-XX ±4% initial match · "
        "TLV output and ALD current remain typical-only · excludes active cycles, cold, ESR, aging, and fitted-assembly effects",
        light=True,
    )
    fig.savefig(temporary, dpi=190)
    plt.close(fig)
    temporary.replace(args.output)
    print(args.output)


if __name__ == "__main__":
    main()
