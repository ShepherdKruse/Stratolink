#!/usr/bin/env python3
"""Visualize the R1 safety-versus-darkness frontier for StratoLink-2."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "analysis/antenna"))
import _style as S

from supercap_charge_ceiling_audit import screen_divider_option


CAPACITANCE_MIN_F = 0.8
FLIGHT3_CONSERVATIVE_FLOOR_V = 3.32
SLEEP_AND_CAP_LEAKAGE_UA = 41.0
TLV8801_MAX_IQ_UA = 0.7
REFERENCE_RESISTOR_MOHM = 10.0


def runtime_h(ceiling_v: float, current_ua: float) -> float:
    return (
        CAPACITANCE_MIN_F
        * (ceiling_v - FLIGHT3_CONSERVATIVE_FLOOR_V)
        / (current_ua * 1e-6)
        / 3600.0
    )


def main() -> None:
    import matplotlib.pyplot as plt

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "analysis/visualization/stratolink2_supercap_divider_frontier.png",
    )
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite evidence: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(f".{args.output.stem}.partial{args.output.suffix}")
    if temporary.exists():
        raise SystemExit(f"refusing to overwrite partial evidence: {temporary}")

    r1 = np.linspace(6.80, 8.30, 301)
    screens = [screen_divider_option(float(value)) for value in r1]
    nominal = np.array([float(item["nominal_ceiling_v"]) for item in screens])
    upper = np.array(
        [float(item["full_temperature_screening_upper_v"]) for item in screens]
    )
    worst_cell = np.array(
        [float(item["worst_initial_cell_v_at_full_temperature_upper"]) for item in screens]
    )
    baseline = np.array(
        [runtime_h(value, SLEEP_AND_CAP_LEAKAGE_UA) for value in nominal]
    )
    active = np.array(
        [
            runtime_h(
                value,
                SLEEP_AND_CAP_LEAKAGE_UA
                + TLV8801_MAX_IQ_UA
                + value / (2.0 * REFERENCE_RESISTOR_MOHM),
            )
            for value in nominal
        ]
    )

    S.use_light()
    fig, axes = plt.subplots(1, 3, figsize=(16, 5.8), sharex=True)
    fig.subplots_adjust(left=0.065, right=0.985, top=0.84, bottom=0.18, wspace=0.25)
    fig.suptitle(
        "StratoLink-2 supercap charge-divider frontier · exact R2 = 4.22 MΩ"
    )

    axes[0].plot(r1, upper, color=S.RED, lw=2.2, label="full-temperature upper")
    axes[0].plot(r1, nominal, color=S.TEAL7, lw=1.7, label="nominal ceiling")
    axes[0].axhline(5.5, color=S.L_TEXT, lw=1.1, ls="--")
    axes[0].fill_between(r1, upper, 5.5, where=upper <= 5.5, color=S.TEAL7, alpha=0.10)
    axes[0].set_ylabel("Total stack voltage (V)")
    axes[0].set_title("Charger / stack ceiling")
    axes[0].legend(frameon=False, fontsize=9)

    axes[1].plot(r1, worst_cell, color=S.WARM, lw=2.2)
    axes[1].axhline(2.75, color=S.L_TEXT, lw=1.1, ls="--")
    axes[1].fill_between(
        r1, worst_cell, 2.75, where=worst_cell <= 2.75,
        color=S.TEAL7, alpha=0.10,
    )
    axes[1].set_ylabel("Worst initial high cell (V)")
    axes[1].set_title("±4% cell-match screen")

    axes[2].plot(r1, baseline, color=S.TEAL7, lw=2.2, label="35 µA sleep + 6 µA cap")
    axes[2].plot(
        r1, active, color=S.TEAL10, lw=1.7,
        label="plus TLV8801 max-IQ reference",
    )
    axes[2].set_ylabel("0.8 F darkness baseline (h)")
    axes[2].set_title("Reserve before active cycles / cold")
    axes[2].legend(frameon=False, fontsize=9)

    markers = (
        (8.25, "fitted 8.25 MΩ", S.RED),
        (7.50, "7.50 MΩ", S.WARM),
        (7.32, "7.32 MΩ", S.TEAL7),
        (7.15, "7.15 MΩ", S.TEAL10),
    )
    for ax in axes:
        for value, label, color in markers:
            ax.axvline(value, color=color, lw=0.9, alpha=0.75)
        ax.set_xlabel("R1 top-divider resistance (MΩ)")
        ax.set_xlim(6.80, 8.30)

    for value, label, color in markers:
        item = screen_divider_option(value)
        axes[0].scatter(value, item["full_temperature_screening_upper_v"], color=color, s=38, zorder=5)
        axes[1].scatter(value, item["worst_initial_cell_v_at_full_temperature_upper"], color=color, s=38, zorder=5)
        axes[2].scatter(value, runtime_h(float(item["nominal_ceiling_v"]), SLEEP_AND_CAP_LEAKAGE_UA), color=color, s=38, zorder=5)

    axes[1].annotate(
        "7.50: 19 mV margin\n7.32: 61 mV margin\n7.15: 102 mV margin",
        xy=(7.32, float(screen_divider_option(7.32)["worst_initial_cell_v_at_full_temperature_upper"])),
        xytext=(6.84, 2.66),
        arrowprops={"arrowstyle": "->", "color": S.TEXT_DIM},
        fontsize=9,
    )
    fitted = screen_divider_option(8.25)
    axes[0].annotate(
        "fitted 8.25 MΩ\n5.592 V screened upper",
        xy=(8.25, float(fitted["full_temperature_screening_upper_v"])),
        xytext=(7.73, 5.56),
        arrowprops={"arrowstyle": "->", "color": S.TEXT_DIM},
        fontsize=9,
    )
    axes[2].annotate(
        "7.50 → 9.12 h\n7.32 → 8.71 h\n7.15 → 8.32 h",
        xy=(7.32, runtime_h(float(screen_divider_option(7.32)["nominal_ceiling_v"]), SLEEP_AND_CAP_LEAKAGE_UA + TLV8801_MAX_IQ_UA + float(screen_divider_option(7.32)["nominal_ceiling_v"]) / (2.0 * REFERENCE_RESISTOR_MOHM))),
        xytext=(6.84, 8.73),
        arrowprops={"arrowstyle": "->", "color": S.TEXT_DIM},
        fontsize=9,
    )

    S.footer(
        fig,
        "Source-bound BQ25570 ±2% + divider tolerance/TCR screen · CAP-XX ±4% initial match · "
        "runtime excludes GPS/radio/watchdog wakes, balancer correction, cold, ESR, and aging",
        light=True,
    )
    fig.savefig(temporary, dpi=190)
    plt.close(fig)
    temporary.replace(args.output)
    print(args.output)


if __name__ == "__main__":
    main()
