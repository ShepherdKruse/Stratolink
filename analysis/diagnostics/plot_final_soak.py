#!/usr/bin/env python3
"""Render the supervised StratoLink-2 PPK2 + TTN soak evidence.

Run with the analysis environment:
  MPLCONFIGDIR=/tmp/stratolink-mpl analysis/.venv/bin/python \
    analysis/diagnostics/plot_final_soak.py
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import math
import os
from pathlib import Path
import sys

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

from evidence_provenance import verify_all as verify_provenance

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "antenna"))
import _style as S  # noqa: E402


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def output_paths(path: Path) -> tuple[Path, Path]:
    temporary = path.with_name(f".{path.stem}.partial{path.suffix}")
    collisions = [item for item in (path, temporary) if item.exists()]
    if collisions:
        raise SystemExit(
            "refusing to overwrite soak-plot evidence: "
            + ", ".join(str(item) for item in collisions)
        )
    return path, temporary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--power",
        type=Path,
        default=HERE / "logs/stratolink2_soak_20260724_power.jsonl",
    )
    parser.add_argument(
        "--handoff-power",
        type=Path,
        default=HERE / "logs/stratolink2_postsoak_power_handoff_20260725.jsonl",
    )
    parser.add_argument(
        "--ttn",
        type=Path,
        default=HERE / "logs/stratolink2_soak_20260724_ttn.jsonl",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=HERE / "logs/stratolink2_soak_20260724_final.json",
        help="preserved complete soak-gate JSON; required for a PASS label",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=HERE / "stratolink2_final_soak.png",
    )
    args = parser.parse_args()
    output, temporary_output = output_paths(args.output)

    power = load_jsonl(args.power)
    handoff = load_jsonl(args.handoff_power) if args.handoff_power.exists() else []
    ttn = load_jsonl(args.ttn)
    assertions = [
        row for row in power
        if row.get("event") in ("ppk2_power_on", "ppk2_power_heartbeat")
    ]
    handoff_assertions = [
        row for row in handoff
        if row.get("event") in ("ppk2_power_on", "ppk2_power_heartbeat")
    ]
    uplinks = [row for row in ttn if row.get("event") == "ttn_uplink"]
    uplinks.sort(key=lambda row: utc(row["utc"]))
    if not assertions or not uplinks:
        raise SystemExit("power and TTN logs must contain assertions/uplinks")

    power_t = [utc(row["utc"]) for row in assertions]
    heartbeat_gap = np.array([
        (later - earlier).total_seconds()
        for earlier, later in zip(power_t, power_t[1:])
    ])
    handoff_t = [utc(row["utc"]) for row in handoff_assertions]
    handoff_gap = np.array([
        (later - earlier).total_seconds()
        for earlier, later in zip(handoff_t, handoff_t[1:])
    ])
    up_t = [utc(row["utc"]) for row in uplinks]
    cadence = np.array([
        (later - earlier).total_seconds()
        for earlier, later in zip(up_t, up_t[1:])
    ])
    telem = [row["telemetry"] for row in uplinks]
    fcnt_values = [row.get("f_cnt") for row in uplinks]
    if (
        fcnt_values
        and fcnt_values[0] is None
        and len(fcnt_values) > 1
        and fcnt_values[1] == 1
    ):
        fcnt_values[0] = 0
    vstor = np.array([row["vstor_mv"] for row in telem], dtype=float)
    source_mv = float(assertions[-1]["source_mv"])
    accel = np.array([
        math.sqrt(
            row["accel_x_cms2"] ** 2
            + row["accel_y_cms2"] ** 2
            + row["accel_z_cms2"] ** 2
        )
        for row in telem
    ])
    temp = np.array([row["temperature_deci_c"] / 10 for row in telem])

    end = [row for row in power if row.get("event") == "ppk2_power_hold_end"]
    handoff_on = [row for row in handoff if row.get("event") == "ppk2_power_on"]
    held = (
        float(end[-1]["held_seconds"])
        if end else (power_t[-1] - power_t[0]).total_seconds()
    )
    transition = (
        (utc(handoff_on[0]["utc"]) - utc(end[-1]["utc"])).total_seconds()
        if end and handoff_on else None
    )
    terminal_control_gap = (
        (utc(end[-1]["utc"]) - power_t[-1]).total_seconds()
        if end else None
    )
    local_shape_ok = (
        len(end) == 1
        and held >= 57600
        and terminal_control_gap is not None
        and 0 <= terminal_control_gap <= 31.5
        and len(handoff_on) == 1
        and len(handoff_assertions) >= 2
        and transition is not None
        and 0 <= transition <= 2
        and {int(row["source_mv"]) for row in handoff_assertions} == {4660}
        and max(
            (int(row.get("reconnects", 0)) for row in handoff_assertions),
            default=0,
        ) == 0
        and max(handoff_gap, default=999) <= 31.5
        and len(uplinks) >= 40
        and all(
            later == earlier + 1
            for earlier, later in zip(fcnt_values, fcnt_values[1:])
            if earlier is not None and later is not None
        )
        and all(value is not None for value in fcnt_values)
        and max(heartbeat_gap, default=999) <= 31.5
    )
    summary = (
        json.loads(args.summary.read_text(encoding="utf-8"))
        if args.summary.exists() else None
    )
    summary_gate = summary.get("final_gate") if isinstance(summary, dict) else None
    summary_pass = (
        isinstance(summary_gate, dict)
        and summary_gate.get("passed") is True
    )
    if summary_pass:
        try:
            verify_provenance(summary.get("provenance"))
        except ValueError as error:
            raise SystemExit(
                f"passed final summary input provenance no longer verifies: {error}"
            ) from error
    summary_matches_logs = bool(
        isinstance(summary, dict)
        and summary.get("power", {}).get("assertions") == len(assertions)
        and summary.get("power", {}).get("hold_end_events") == len(end)
        and summary.get("uplinks", {}).get("count") == len(uplinks)
    )
    if summary_pass and not summary_matches_logs:
        raise SystemExit(
            "passed final summary no longer matches the raw logs; refresh the "
            "Supabase export and final summary before plotting"
        )
    if summary_pass and not local_shape_ok:
        raise SystemExit(
            "passed final summary contradicts the plot's raw power/uplink checks"
        )
    final_pass = summary_pass and summary_matches_logs and local_shape_ok
    if final_pass:
        gate_label = "SOAK GATE PASS"
    elif isinstance(summary_gate, dict):
        gate_label = "SOAK GATE FAIL"
    else:
        gate_label = "SOAK IN PROGRESS"

    S.use_light()
    fig, axes = plt.subplots(4, 2, figsize=(18, 15))
    fig.suptitle(
        "StratoLink-2 supervised flight-firmware precursor soak · "
        f"{gate_label}"
    )

    ax = axes[0, 0]
    ax.plot(up_t, vstor, marker="o", lw=1.2, color=S.TEAL7, label="VSTOR telemetry")
    ax.axhline(source_mv, color=S.TEAL10, lw=1.4, label="PPK2 source 4660 mV")
    ax.axhline(5363, color=S.WARM, ls="-.", lw=1,
               label="nominal VBAT_OV 5363 mV")
    ax.axhline(3600, color=S.WARM, ls="--", lw=1, label="GPS floor 3600 mV")
    ax.axhline(3000, color=S.RED, ls=":", lw=1, label="TX floor 3000 mV")
    ax.set_ylabel("millivolts")
    ax.set_ylim(2800, max(5500, float(vstor.max()) + 150))
    ax.set_title(
        f"Supply · VSTOR {vstor.min():.0f}–{vstor.max():.0f} mV · "
        f"source delta {(source_mv-vstor).min():.0f}–{(source_mv-vstor).max():.0f} mV"
    )
    ax.legend(fontsize=8, loc="lower left")

    ax = axes[0, 1]
    ax.plot(power_t[1:], heartbeat_gap, marker=".", lw=0.9,
            color=S.TEAL7, label="primary supervisor")
    if len(handoff_gap):
        ax.plot(handoff_t[1:], handoff_gap, marker=".", lw=0.9,
                color=S.TEAL10, label="standby supervisor")
    ax.axhline(31.5, color=S.RED, ls="--", lw=1.2, label="31.5 s gate")
    if transition is not None:
        transition_x = utc(handoff_on[0]["utc"])
        transition_y = min(transition, 34.0)
        ax.scatter(
            [transition_x],
            [transition_y],
            marker="X",
            s=75,
            color=S.RED,
            zorder=5,
            label=f"handoff {transition:.3f} s",
        )
        if transition > 35:
            ax.annotate(
                f"{transition:.3f} s\n(out of range)",
                xy=(transition_x, transition_y),
                xytext=(-8, -6),
                textcoords="offset points",
                ha="right",
                va="top",
                color=S.RED,
                fontsize=8,
            )
    ax.set_ylabel("assertion gap (s)")
    ax.set_ylim(0, 35)
    transition_text = "pending" if transition is None else f"{transition:.3f} s"
    ax.set_title(
        f"PPK2 control continuity · max {max(heartbeat_gap):.3f} s · "
        f"handoff {transition_text}"
    )
    ax.legend(fontsize=8, loc="lower left")

    ax = axes[1, 0]
    idx = np.arange(1, len(cadence) + 1)
    scheduled = (cadence >= 1100) & (cadence <= 1350)
    scheduled_temp = temp[1:][scheduled]
    scheduled_cadence = cadence[scheduled]
    cadence_temp_corr = (
        float(np.corrcoef(scheduled_cadence, scheduled_temp)[0, 1])
        if len(scheduled_cadence) >= 3
        and np.std(scheduled_cadence) > 0
        and np.std(scheduled_temp) > 0
        else None
    )
    ax.axhspan(1200, 1350, color=S.TEAL7, alpha=0.12,
               label="scheduled acceptance 1200–1350 s")
    if np.any(scheduled):
        scheduled_marks = ax.scatter(
            idx[scheduled],
            scheduled_cadence,
            c=scheduled_temp,
            cmap="viridis",
            s=38,
            zorder=3,
            label="scheduled interval",
        )
        colorbar = fig.colorbar(scheduled_marks, ax=ax, pad=0.02)
        colorbar.set_label("end temperature (°C)")
    unscheduled = ~scheduled
    if np.any(unscheduled):
        ax.scatter(
            idx[unscheduled],
            cadence[unscheduled],
            color=S.WARM,
            marker="X",
            s=58,
            zorder=4,
            label="short/long wake",
        )
    ax.set_xlabel("uplink interval")
    ax.set_ylabel("seconds")
    corr_text = (
        "n/a" if cadence_temp_corr is None else f"{cadence_temp_corr:+.3f}"
    )
    ax.set_title(
        f"Cadence vs temperature · {sum(scheduled)} scheduled · "
        f"{sum(unscheduled)} excluded · r={corr_text} descriptive"
    )
    ax.legend(fontsize=8)

    ax = axes[1, 1]
    fcnt = np.array(fcnt_values)
    ax.plot(up_t, fcnt, marker="o", lw=1.2, color=S.TEAL7)
    ax.set_ylabel("LoRaWAN FCntUp")
    ax.set_title(
        f"Counter continuity · {fcnt[0]}→{fcnt[-1]} · "
        f"{'contiguous' if np.all(np.diff(fcnt) == 1) else 'DISCONTINUITY'}"
    )

    ax = axes[2, 0]
    rssi = np.array([row["rssi_dbm"] for row in uplinks], dtype=float)
    ax.plot(up_t, rssi, marker="o", color=S.TEAL7, label="RSSI")
    ax.set_ylabel("RSSI (dBm)")
    ax2 = ax.twinx()
    snr = np.array([row["snr_db"] for row in uplinks], dtype=float)
    ax2.plot(up_t, snr, marker="s", color=S.WARM, label="SNR")
    ax2.set_ylabel("SNR (dB)", color=S.WARM)
    ax.set_title(
        f"Gateway link · RSSI {rssi.min():.0f}–{rssi.max():.0f} dBm · "
        f"SNR {snr.min():.2f}–{snr.max():.2f} dB"
    )
    ax.legend(fontsize=8, loc="lower left")
    ax2.legend(fontsize=8, loc="lower right")

    ax = axes[2, 1]
    ax.plot(up_t, temp, marker="o", color=S.TEAL7, label="TMP117")
    ax.set_ylabel("temperature (°C)")
    ax2 = ax.twinx()
    pressure = np.array([row["pressure_deci_hpa"] / 10 for row in telem])
    ax2.plot(up_t, pressure, marker="s", color=S.TEAL10, label="MS5611")
    ax2.set_ylabel("pressure (hPa)", color=S.TEAL10)
    ax.set_title(
        f"Environmental sensors · {temp.min():.1f}–{temp.max():.1f} °C · "
        f"{pressure.min():.1f}–{pressure.max():.1f} hPa"
    )
    ax.legend(fontsize=8, loc="lower left")
    ax2.legend(fontsize=8, loc="lower right")

    ax = axes[3, 0]
    solar = np.array([row["solar_mv"] for row in telem], dtype=float)
    lux = np.array([row["ambient_lux"] for row in telem], dtype=float)
    ax.plot(up_t, solar, marker="o", color=S.WARM, label="solar ADC")
    ax.set_ylabel("solar (mV)")
    ax2 = ax.twinx()
    ax2.plot(up_t, lux, marker="s", color=S.TEAL7, label="LTR390 ambient")
    ax2.set_ylabel("ambient (lux)", color=S.TEAL7)
    ax.set_title(
        f"Optical/day-night coherence · solar {solar.min():.0f}–{solar.max():.0f} mV · "
        f"ambient {lux.min():.0f}–{lux.max():.0f} lux"
    )
    ax.legend(fontsize=8, loc="upper right")
    ax2.legend(fontsize=8, loc="center right")

    ax = axes[3, 1]
    ax.plot(up_t, accel, marker="o", color=S.TEAL7)
    ax.axhline(981, color=S.TEAL10, ls=":", lw=1.2, label="1 g")
    ax.axhline(350, color=S.RED, ls="--", lw=1.2, label="freefall threshold")
    ax.set_ylabel("|acceleration| (cm/s²)")
    ax.set_title(
        f"LIS2DH12 plausibility · {accel.min():.0f}–{accel.max():.0f} cm/s²"
    )
    ax.legend(fontsize=8)

    for ax in axes.flat:
        lines = ax.get_lines()
        if lines and any(
            isinstance(value, datetime) for value in lines[0].get_xdata()
        ):
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
            ax.tick_params(axis="x", rotation=25)

    S.footer(
        fig,
        f"PPK2 source={source_mv:.0f} mV · held={held/3600:.2f} h · "
        f"uplinks={len(uplinks)} · {gate_label.lower()} · "
        "not overall launch clearance · "
        "generated by analysis/diagnostics/plot_final_soak.py",
        light=True,
    )
    fig.tight_layout(rect=(0, 0.02, 1, 0.97))
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(temporary_output, dpi=170)
    plt.close(fig)
    try:
        os.link(temporary_output, output)
    except FileExistsError as error:
        raise SystemExit(
            f"refusing to overwrite soak-plot evidence: {output}"
        ) from error
    finally:
        temporary_output.unlink(missing_ok=True)
    print(output)


if __name__ == "__main__":
    main()
