#!/usr/bin/env python3
"""Plot passive LongFast-band energy against a precursor TTN wake cycle.

The expected CTT/relay boundaries are approximate because TTN timestamps the
gateway reception, not the target's exact end-of-TX time. The plot is alignment
evidence only: an RTL-SDR envelope cannot identify or decode a relay packet.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-prefix", type=Path, required=True)
    parser.add_argument("--ttn", type=Path, required=True)
    parser.add_argument("--fcnt", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--class-a-seconds", type=float, default=7.0)
    parser.add_argument("--ctt-seconds", type=float, default=60.0)
    args = parser.parse_args()

    # Keep --help available on evidence-review hosts without the optional plot
    # stack. Rendering imports are required only for a complete invocation.
    import matplotlib.pyplot as plt
    import numpy as np

    if args.output.exists():
        raise SystemExit(f"refusing to overwrite SDR alignment plot: {args.output}")
    summary = json.loads(args.capture_prefix.with_suffix(".json").read_text())
    capture = np.load(args.capture_prefix.with_suffix(".npz"))
    time_s = capture["time_seconds"]
    signal_db = capture["signal_power_db"]

    frame = None
    for line in args.ttn.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("event") == "ttn_uplink" and row.get("f_cnt") == args.fcnt:
            frame = row
    if frame is None:
        raise SystemExit(f"TTN frame {args.fcnt} not found")

    capture_start = parse_utc(summary["created_utc"])
    uplink_s = (parse_utc(frame["received_at"]) - capture_start).total_seconds()
    ctt_start_s = uplink_s + args.class_a_seconds
    relay_start_s = ctt_start_s + args.ctt_seconds
    duration_s = float(summary["duration_seconds"])

    fig, (overview, zoom) = plt.subplots(
        2, 1, figsize=(13, 7.2), sharey=True,
        gridspec_kw={"height_ratios": [1, 1.25]},
    )
    for axis in (overview, zoom):
        axis.plot(time_s, signal_db, color="#315b7d", linewidth=0.45,
                  rasterized=True)
        axis.axhline(summary["threshold_db"], color="#bd4f3c", linewidth=1,
                     linestyle="--", label="burst threshold")
        axis.axvline(uplink_s, color="#6a3d9a", linewidth=1.2,
                     label=f"TTN fCnt {args.fcnt}")
        axis.axvspan(ctt_start_s, min(relay_start_s, duration_s),
                     color="#e6ab02", alpha=0.14,
                     label="approx. precursor CTT window")
        if relay_start_s < duration_s:
            axis.axvspan(relay_start_s, duration_s, color="#1b9e77",
                         alpha=0.12, label="approx. LongFast window")
        for burst in summary["bursts"]:
            if burst["longfast_duration_candidate"]:
                axis.scatter(burst["start_seconds"], burst["peak_db"], s=14,
                             color="#d95f02", zorder=3)
        axis.grid(alpha=0.16)
        axis.set_ylabel("relative band power (dB)")

    overview.set_xlim(0, duration_s)
    overview.set_title(
        "906.875 MHz passive envelope — timing alignment only, not packet decode"
    )
    overview.legend(loc="upper right", ncol=2, fontsize=8)
    zoom.set_xlim(max(0, uplink_s - 10), duration_s)
    zoom.set_xlabel("seconds from SDR capture start")
    zoom.set_title("Zoom on fCnt wake, precursor CTT slice, and LongFast handoff")
    fig.text(
        0.01, 0.01,
        "Running soak precursor had CTT enabled. The new StratoLink-2 flight "
        "default disables CTT; shaded boundaries include approximate Class-A "
        "latency and must be confirmed with exact-ELF counters.",
        fontsize=8, color="#444444",
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=180)
    print(args.output)


if __name__ == "__main__":
    main()
