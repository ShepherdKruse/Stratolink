#!/usr/bin/env python3
"""Bind the flight payload ceilings to LoRa airtime and AS923 dwell limits."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
RP002_URL = (
    "https://resources.lora-alliance.org/technical-specifications/"
    "rp002-1-0-5-lorawan-regional-parameters"
)
TTN_PLAN_URL = (
    "https://github.com/TheThingsNetwork/lorawan-frequency-plans/"
    "blob/master/AS_920_923.yml"
)


def macro(text: str, name: str) -> int:
    match = re.search(
        rf"^#define\s+{re.escape(name)}\s+(\d+)(?:u)?(?:\s|$)",
        text,
        re.MULTILINE,
    )
    if not match:
        raise ValueError(f"missing integer macro {name}")
    return int(match.group(1))


def lora_toa_ms(payload_bytes: int, sf: int, bw_hz: int = 125_000) -> float:
    """Explicit-header, CRC-on, CR 4/5, preamble-8 LoRa time on air."""
    if payload_bytes < 0:
        raise ValueError("negative payload length")
    low_rate_optimize = 1 if sf >= 11 and bw_hz == 125_000 else 0
    numerator = 8 * payload_bytes - 4 * sf + 28 + 16
    denominator = 4 * (sf - 2 * low_rate_optimize)
    payload_symbols = 8 + max(math.ceil(numerator / denominator) * 5, 0)
    symbol_ms = (2**sf) / bw_hz * 1000
    return (8 + 4.25 + payload_symbols) * symbol_ms


def audit(root: Path = ROOT) -> dict:
    config = (root / "firmware/include/config.h").read_text(encoding="utf-8")
    telemetry = (root / "firmware/include/telemetry.h").read_text(encoding="utf-8")
    lorawan_h = (root / "firmware/include/lorawan.h").read_text(encoding="utf-8")
    lorawan_cpp = (root / "firmware/src/lorawan.cpp").read_text(encoding="utf-8")

    telemetry_app_bytes = macro(telemetry, "TELEMETRY_PAYLOAD_SIZE")
    maximum_app_bytes = macro(lorawan_h, "LORAWAN_PAYLOAD_MAX")
    cadence_seconds = macro(config, "SLEEP_INTERVAL_FULL_SEC")
    auxiliary_interval = macro(config, "AUX_UPLINK_INTERVAL_CYCLES")
    burst_max = macro(config, "BURST_MAX_CYCLES")

    as923 = re.search(
        r"static const lora_region_t LORA_AS923\s*=\s*\{(.*?)\n\};",
        lorawan_cpp,
        re.DOTALL,
    )
    if not as923:
        raise ValueError("AS923 region table not found")
    table = re.sub(r"/\*.*?\*/", "", as923.group(1), flags=re.DOTALL)
    if "AS923_FREQS," not in table:
        raise ValueError("AS923 frequency-table reference changed")
    values = re.findall(
        r"\d+(?:\.\d+)?",
        table.split("AS923_FREQS,", 1)[1],
    )
    # tx_sf is the final numeric field; join_sf is the seventh numeric field
    # after tx_ch_count/rx2/rx1_base/rx1_step/rx1_mod.
    if len(values) < 14:
        raise ValueError("AS923 region table shape changed")
    join_sf = int(float(values[5]))
    tx_sf = int(float(values[-2]))
    tx_bw_khz = float(values[-1])
    if tx_bw_khz != 125.0:
        raise ValueError("airtime audit currently requires AS923 BW125")

    lorawan_overhead = 13  # MHDR + FHDR(no FOpts) + FPort + MIC
    primary_phy_bytes = telemetry_app_bytes + lorawan_overhead
    maximum_phy_bytes = maximum_app_bytes + lorawan_overhead
    primary_ms = lora_toa_ms(primary_phy_bytes, tx_sf)
    maximum_ms = lora_toa_ms(maximum_phy_bytes, tx_sf)
    join_ms = lora_toa_ms(23, join_sf)

    dwell_limit_ms = 400.0
    uplinks_per_day = 86_400 // cadence_seconds
    auxiliaries_per_day = uplinks_per_day // auxiliary_interval
    normal_daily_ms = uplinks_per_day * primary_ms + auxiliaries_per_day * maximum_ms
    fault_plus_one_join_ms = normal_daily_ms + burst_max * primary_ms + join_ms

    gates = {
        "as923_primary_under_400ms": primary_ms < dwell_limit_ms,
        "as923_maximum_aux_under_400ms": maximum_ms < dwell_limit_ms,
        "as923_join_request_under_400ms": join_ms < dwell_limit_ms,
        "normal_daily_ttn_airtime_under_30s": normal_daily_ms < 30_000,
        "modeled_fault_burst_plus_one_join_under_30s": fault_plus_one_join_ms < 30_000,
    }
    return {
        "passed": all(gates.values()),
        "scope": (
            "nominal LoRa PHY airtime from source constants; not jurisdictional "
            "certification, oscillator/radio HIL, or a universal regulatory claim"
        ),
        "sources": {
            "lorawan_regional_parameters": RP002_URL,
            "ttn_as_920_923_plan": TTN_PLAN_URL,
        },
        "source_constants": {
            "telemetry_application_bytes": telemetry_app_bytes,
            "maximum_application_bytes": maximum_app_bytes,
            "lorawan_overhead_bytes": lorawan_overhead,
            "full_cadence_seconds": cadence_seconds,
            "auxiliary_interval_cycles": auxiliary_interval,
            "burst_max_cycles": burst_max,
            "as923_join_sf": join_sf,
            "as923_tx_sf": tx_sf,
            "as923_tx_bw_khz": tx_bw_khz,
        },
        "airtime": {
            "primary_phy_bytes": primary_phy_bytes,
            "primary_ms": round(primary_ms, 6),
            "maximum_aux_phy_bytes": maximum_phy_bytes,
            "maximum_aux_ms": round(maximum_ms, 6),
            "maximum_aux_dwell_margin_ms": round(dwell_limit_ms - maximum_ms, 6),
            "join_request_phy_bytes": 23,
            "join_request_ms": round(join_ms, 6),
            "normal_daily_ms": round(normal_daily_ms, 6),
            "modeled_fault_burst_plus_one_join_ms": round(fault_plus_one_join_ms, 6),
        },
        "gates": gates,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit()
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        if args.output.exists():
            raise SystemExit(f"refusing to overwrite airtime evidence: {args.output}")
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
