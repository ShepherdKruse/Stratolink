#!/usr/bin/env python3
"""Render the scoped StratoLink-2 launch-readiness evidence matrix."""

from __future__ import annotations

import argparse
from collections import Counter
import os
from pathlib import Path
import sys
import textwrap

HERE = Path(__file__).resolve().parent

DEFAULT_MATRIX = HERE / "STRATOLINK2_LAUNCH_READINESS_20260724.md"

DOMAINS = {
    "Hardware & power": {
        "Schematic/PCB rule sign-off",
        "PPK2 powers the board continuously",
        "Board survives normal wake/sleep/uplink cycles",
        "Voltage telemetry and power tiers",
        "Flight-representative sleep current",
        "SX1262 quiescence after a radio/PHY fault",
        "Supercap charge, cell balance, sag, brownout, and recovery",
        "Flight-temperature margin",
    },
    "GNSS & sensors": {
        "GPS stale-fix prevention",
        "GPS wedge recovery",
        "GPS shutdown confirmation",
        "Honest no-GPS / impossible-PVT telemetry",
        "TMP117 temperature",
        "MS5611 pressure",
        "LIS2DH12 acceleration/freefall path",
        "LTR390 light/UV",
        "LTR390 standby after a transport fault",
        "Shared I2C bus fault containment",
        "Integrated sensor-stream continuity",
        "Acoustic event detector",
    },
    "RF & flight protocol": {
        "LoRaWAN uplink",
        "LoRaWAN OTAA receive windows/retry bound",
        "SF9 link margin",
        "Monopole + solar-panel RF assembly",
        "Suspension / antenna attitude",
        "LoRaWAN downlink command receive",
        "Remote flight control",
        "US TTN regional configuration",
        "EU TTN regional configuration",
        "AS923 TTN regional configuration",
        "AU915 global path",
        "Region geofence and stale-location lease",
        "DevNonce / rejoin and session durability",
        "Meshtastic LongFast receive/relay",
        "Wildlife CTT decode/queue/uplink format",
        "B2B wire/auth/dedup/TTL/fairness",
        "Auxiliary TTN airtime budget",
    },
    "Backend & release": {
        "Web fPort-11/fPort-12 and telemetry parsing",
        "TTN-to-Supabase delivery fidelity",
        "TTN webhook authentication/replay integrity",
        "TTN outage recovery",
        "StratoLink-2 production registration",
        "Wildlife/B2B persistence in Supabase",
        "Web dependency exposure",
        "Credential hygiene",
        "Flight telemetry observability",
        "Final flight binary",
    },
}


def parse_matrix(path: Path) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if (
            not line.startswith("| ")
            or line.startswith("|---")
            or "Subsystem / claim" in line
        ):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) >= 4:
            rows.append((cells[0], cells[1]))
    if not rows:
        raise SystemExit("no evidence rows found in readiness matrix")
    return rows


def category(status: str) -> str:
    upper = status.upper()
    if (
        "BLOCKED" in upper
        or "NOT FROZEN" in upper
        or "DO NOT FLASH" in upper
    ):
        return "Blocked"
    if upper.startswith("PROVEN"):
        return "Proven (scoped)"
    if upper.startswith(
        (
            "PARTIAL",
            "CONFIGURED",
            "MODELED",
            "PREPARED LOCALLY",
            "CORRECTED IN CODE",
            "IMPLEMENTED",
            "FROZEN AND VERIFIED",
        )
    ):
        return "Partial / modeled / configured"
    raise SystemExit(f"unrecognized readiness status: {status}")


def domain_for(claim: str) -> str:
    matches = [domain for domain, claims in DOMAINS.items() if claim in claims]
    if len(matches) != 1:
        raise SystemExit(f"readiness claim is unmapped or multiply mapped: {claim}")
    return matches[0]


def output_paths(path: Path) -> tuple[Path, Path]:
    temporary = path.with_name(f".{path.stem}.partial{path.suffix}")
    collisions = [item for item in (path, temporary) if item.exists()]
    if collisions:
        raise SystemExit(
            "refusing to overwrite readiness-plot evidence: "
            + ", ".join(str(item) for item in collisions)
        )
    return path, temporary


def main() -> None:
    # Keep matrix parsing/category validation lightweight and dependency-free
    # for the regression test. Rendering imports belong only to the render
    # path, where MPLCONFIGDIR is set by the qualification command.
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    sys.path.insert(0, str(HERE.parent / "antenna"))
    import _style as S

    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument(
        "--output",
        type=Path,
        default=HERE / "stratolink2_launch_readiness.png",
    )
    args = parser.parse_args()
    output, temporary_output = output_paths(args.output)

    rows = parse_matrix(args.matrix)
    expected = set().union(*DOMAINS.values())
    duplicates = sorted(
        claim for claim, count in Counter(claim for claim, _ in rows).items()
        if count != 1
    )
    if duplicates:
        raise SystemExit(f"duplicate readiness claims: {duplicates}")
    actual = {claim for claim, _ in rows}
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise SystemExit(
            f"readiness mapping mismatch; missing={missing}, extra={extra}"
        )

    grouped = {
        domain: [(claim, status) for claim, status in rows if domain_for(claim) == domain]
        for domain in DOMAINS
    }
    counts = {
        label: sum(category(status) == label for _, status in rows)
        for label in ("Proven (scoped)", "Partial / modeled / configured", "Blocked")
    }

    S.use_light()
    colors = {
        "Proven (scoped)": S.TEAL7,
        "Partial / modeled / configured": S.WARM,
        "Blocked": S.RED,
    }
    fig, axes = plt.subplots(1, 4, figsize=(22, 13))
    # Reserve figure-owned space explicitly for the suptitle, legend, and
    # footer. tight_layout cannot reason about the footer text added by the
    # shared style helper and emitted a warning that could conceal real
    # clipping in an automated evidence render.
    fig.subplots_adjust(
        left=0.025,
        right=0.985,
        top=0.925,
        bottom=0.105,
        wspace=0.22,
    )
    fig.suptitle(
        "StratoLink-2 launch-readiness evidence · "
        f"{counts['Proven (scoped)']} scoped-proven · "
        f"{counts['Partial / modeled / configured']} partial · "
        f"{counts['Blocked']} blocked"
    )

    for ax, (domain, domain_rows) in zip(axes, grouped.items()):
        ax.set_xlim(0, 1)
        ax.set_ylim(-0.7, len(domain_rows) - 0.3)
        ax.invert_yaxis()
        ax.set_title(f"{domain} · {len(domain_rows)} gates", loc="left")
        ax.grid(False)
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)

        for index, (claim, status) in enumerate(domain_rows):
            label = category(status)
            ax.scatter(
                [0.035],
                [index],
                s=75,
                color=colors[label],
                marker={"Proven (scoped)": "o", "Partial / modeled / configured": "^",
                        "Blocked": "X"}[label],
                zorder=3,
            )
            wrapped = "\n".join(textwrap.wrap(claim, width=34))
            ax.text(0.09, index - 0.08, wrapped, ha="left", va="center", fontsize=9)
            status_short = status if len(status) <= 44 else status[:41] + "…"
            ax.text(
                0.09,
                index + 0.28,
                status_short,
                ha="left",
                va="center",
                fontsize=7.5,
                color=S.TEXT_DIM,
            )
        for boundary in [i + 0.5 for i in range(len(domain_rows) - 1)]:
            ax.axhline(boundary, color=S.GRID, lw=0.55, zorder=0)

    legend = [
        Line2D(
            [0],
            [0],
            marker={"Proven (scoped)": "o", "Partial / modeled / configured": "^",
                    "Blocked": "X"}[label],
            color="none",
            markerfacecolor=colors[label],
            markeredgecolor=colors[label],
            markersize=8,
            label=f"{label}: {counts[label]}",
        )
        for label in counts
    ]
    fig.legend(
        handles=legend,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.028),
        ncol=3,
        frameon=False,
    )
    S.footer(
        fig,
        "Status is scoped to each claim; any partial or blocked required gate "
        "prevents overall launch clearance · source: "
        "STRATOLINK2_LAUNCH_READINESS_20260724.md",
        light=True,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(temporary_output, dpi=170)
    plt.close(fig)
    try:
        os.link(temporary_output, output)
    except FileExistsError as error:
        raise SystemExit(
            f"refusing to overwrite readiness-plot evidence: {output}"
        ) from error
    finally:
        temporary_output.unlink(missing_ok=True)
    print(output)


if __name__ == "__main__":
    main()
