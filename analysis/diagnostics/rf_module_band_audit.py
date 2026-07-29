#!/usr/bin/env python3
"""Bind StratoLink's RF claims to the exact fitted RAK3172 orderable SKU."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import re
from statistics import fmean


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DEFAULT_BOM = ROOT / "hardware" / "gerbers" / "production_files" / "BOM-stratolink.csv"
DEFAULT_TELEMETRY = HERE.parent / "antenna" / "data" / "telemetry_raw.csv"
DEFAULT_LORAWAN_SOURCE = ROOT / "firmware" / "src" / "lorawan.cpp"
DEFAULT_CONFIG = ROOT / "firmware" / "include" / "config.h"
RADIO_DESIGNATOR = "U2"
RADIO_LCSC = "C18548052"
RADIO_SKU = "RAK3172-9-SM-NI"
SKU_SPECIFIED_FAMILIES = ("US915", "AU915", "KR920", "AS923")
SKU_UNSPECIFIED_CLAIMS = ("EU868", "CTT434")
RAK_SOURCE = "https://docs.rakwireless.com/product-categories/wisduo/rak3172-module/datasheet/"
LCSC_SOURCE = "https://www.lcsc.com/product-detail/C18548052.html"


def numeric_summary(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    return {
        "min": min(values),
        "mean": round(fmean(values), 3),
        "max": max(values),
    }


def verify_bom(path: Path) -> None:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    matches = [
        row for row in rows
        if row.get("Designator") == RADIO_DESIGNATOR
        and (row.get("LCSC") or row.get("LCSC Part #")) == RADIO_LCSC
    ]
    if len(matches) != 1:
        raise SystemExit(
            f"expected one {RADIO_DESIGNATOR}/{RADIO_LCSC} BOM row; "
            f"found {len(matches)}"
        )


def parse_firmware_claims(lorawan_path: Path, config_path: Path) -> dict[str, object]:
    lorawan = lorawan_path.read_text(encoding="utf-8")
    config = config_path.read_text(encoding="utf-8")
    eu_match = re.search(
        r"EU868_FREQS\[\]\s*=\s*\{([^}]+)\}", lorawan
    )
    ctt_match = re.search(
        r"#define\s+CTT_FREQ_MHZ\s+([0-9.]+)", config
    )
    ctt_enable_match = re.search(
        r"#define\s+CTT_LISTEN_ENABLE\s+(true|false|0|1)\b", config
    )
    if not eu_match or not ctt_match or not ctt_enable_match:
        raise SystemExit("could not bind current EU868/CTT frequencies from source")
    eu_frequencies_mhz = [
        float(token.strip().removesuffix("f"))
        for token in eu_match.group(1).split(",")
    ]
    ctt_enabled = ctt_enable_match.group(1) in ("true", "1")
    return {
        "eu868_uplink_frequencies_mhz": eu_frequencies_mhz,
        "ctt_listen_enabled": ctt_enabled,
        "ctt_frequency_mhz": float(ctt_match.group(1)),
    }


def historical_eu_evidence(path: Path) -> dict[str, object]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = [row for row in csv.DictReader(handle) if row.get("region") == "EU"]
    frequencies = [int(float(row["frequency_hz"])) for row in rows if row.get("frequency_hz")]
    frequency_counts = {
        str(frequency): frequencies.count(frequency)
        for frequency in sorted(set(frequencies))
    }
    times = [row["time"] for row in rows if row.get("time")]
    return {
        "received_uplinks": len(rows),
        "device_ids": sorted({row["device_id"] for row in rows}),
        "first_utc": min(times) if times else None,
        "last_utc": max(times) if times else None,
        "frequency_counts_hz": frequency_counts,
        "rssi_dbm": numeric_summary([
            float(row["rssi"]) for row in rows if row.get("rssi")
        ]),
        "snr_db": numeric_summary([
            float(row["snr"]) for row in rows if row.get("snr")
        ]),
        "interpretation": (
            "These received TTN uplinks prove that the flown assembly radiated "
            "usable 868 MHz packets under those particular conditions. They do "
            "not establish the exact SKU's specified band, conducted output, "
            "receiver sensitivity, antenna match, certification, cold margin, "
            "or assembly-to-assembly repeatability."
        ),
    }


def audit(
    bom_path: Path,
    telemetry_path: Path,
    lorawan_path: Path,
    config_path: Path,
) -> dict[str, object]:
    verify_bom(bom_path)
    firmware = parse_firmware_claims(lorawan_path, config_path)
    historical = historical_eu_evidence(telemetry_path)
    return {
        "status": "BLOCKED_PENDING_EXACT_SKU_RF_QUALIFICATION",
        "fitted_radio": {
            "designator": RADIO_DESIGNATOR,
            "lcsc_part": RADIO_LCSC,
            "resolved_orderable_sku": RADIO_SKU,
            "manufacturer_specified_families": list(SKU_SPECIFIED_FAMILIES),
            "current_firmware_unspecified_claims": [
                "EU868",
                *(["CTT434"] if firmware["ctt_listen_enabled"] else []),
            ],
        },
        "current_firmware": firmware,
        "historical_eu868": historical,
        "sources": {
            "rak_ordering_table": RAK_SOURCE,
            "lcsc_exact_part_mapping": LCSC_SOURCE,
            "bom": str(bom_path),
            "lorawan_source": str(lorawan_path),
            "config_source": str(config_path),
            "telemetry": str(telemetry_path),
        },
        "required_gate": (
            "Obtain manufacturer confirmation for 868 MHz use of the exact -9 "
            "SKU or qualify conducted TX power/RX sensitivity, installed-antenna "
            "match, cold operation, and end-to-end EU868 join/uplink/downlink at "
            "launch-relevant margin. Otherwise use hardware whose exact ordering "
            "code covers every claimed flight band."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bom", type=Path, default=DEFAULT_BOM)
    parser.add_argument("--telemetry", type=Path, default=DEFAULT_TELEMETRY)
    parser.add_argument("--lorawan-source", type=Path, default=DEFAULT_LORAWAN_SOURCE)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    print(json.dumps(audit(args.bom, args.telemetry, args.lorawan_source, args.config), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
