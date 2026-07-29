#!/usr/bin/env python3
"""Regression checks for exact-SKU RF-band qualification."""

from __future__ import annotations

import csv
from pathlib import Path
import tempfile

import rf_module_band_audit as rf


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="stratolink-rf-band-audit-") as raw:
        directory = Path(raw)
        bom = directory / "bom.csv"
        telemetry = directory / "telemetry.csv"
        lorawan = directory / "lorawan.cpp"
        config = directory / "config.h"
        write_csv(
            bom,
            ["Comment", "Designator", "Footprint", "LCSC"],
            [{
                "Comment": "RAK3172",
                "Designator": "U2",
                "Footprint": "RAK3172",
                "LCSC": rf.RADIO_LCSC,
            }],
        )
        fields = ["device_id", "time", "region", "frequency_hz", "rssi", "snr"]
        write_csv(
            telemetry,
            fields,
            [
                {
                    "device_id": "eu-fixture",
                    "time": "2026-05-28T00:00:00+00:00",
                    "region": "EU",
                    "frequency_hz": "868100000",
                    "rssi": "-115",
                    "snr": "-1.2",
                },
                {
                    "device_id": "us-fixture",
                    "time": "2026-05-17T00:00:00+00:00",
                    "region": "US",
                    "frequency_hz": "904100000",
                    "rssi": "-60",
                    "snr": "10",
                },
            ],
        )
        lorawan.write_text(
            "static const float EU868_FREQS[] = {868.1f, 868.3f, 868.5f};\n",
            encoding="utf-8",
        )
        config.write_text(
            "#define CTT_LISTEN_ENABLE true\n#define CTT_FREQ_MHZ 434.0\n",
            encoding="utf-8",
        )
        report = rf.audit(bom, telemetry, lorawan, config)

    assert report["status"] == "BLOCKED_PENDING_EXACT_SKU_RF_QUALIFICATION"
    fitted = report["fitted_radio"]
    assert fitted["resolved_orderable_sku"] == "RAK3172-9-SM-NI"
    assert "US915" in fitted["manufacturer_specified_families"]
    assert "EU868" not in fitted["manufacturer_specified_families"]
    assert fitted["current_firmware_unspecified_claims"] == ["EU868", "CTT434"]
    assert report["current_firmware"] == {
        "eu868_uplink_frequencies_mhz": [868.1, 868.3, 868.5],
        "ctt_listen_enabled": True,
        "ctt_frequency_mhz": 434.0,
    }
    history = report["historical_eu868"]
    assert history["received_uplinks"] == 1
    assert history["frequency_counts_hz"] == {"868100000": 1}
    assert history["rssi_dbm"] == {"min": -115.0, "mean": -115.0, "max": -115.0}

    live = rf.audit(
        rf.DEFAULT_BOM,
        rf.DEFAULT_TELEMETRY,
        rf.DEFAULT_LORAWAN_SOURCE,
        rf.DEFAULT_CONFIG,
    )
    assert live["status"] == "BLOCKED_PENDING_EXACT_SKU_RF_QUALIFICATION"
    assert live["current_firmware"]["ctt_listen_enabled"] is False
    assert live["fitted_radio"]["current_firmware_unspecified_claims"] == ["EU868"]
    assert live["historical_eu868"]["received_uplinks"] == 142
    assert live["historical_eu868"]["frequency_counts_hz"] == {
        "868100000": 49,
        "868300000": 47,
        "868500000": 46,
    }
    readiness = (
        rf.HERE / "STRATOLINK2_LAUNCH_READINESS_20260724.md"
    ).read_text(encoding="utf-8")
    assert (
        "EU TTN regional configuration | BLOCKED ON EXACT MODULE RF QUALIFICATION"
        in readiness
    )
    print("PASS: exact fitted SKU fails closed for unspecified RF claims")


if __name__ == "__main__":
    main()
