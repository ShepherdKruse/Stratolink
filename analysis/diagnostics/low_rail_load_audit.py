#!/usr/bin/env python3
"""Source-bound screen for StratoLink-2 GPS/TX low-rail thresholds.

This is deliberately an ohmic first-order screen, not qualification. The
BQ25570 current capability and transient response are not guaranteed for the
exact 3.312 V output, fitted passives, 100 mA MAX-M10S startup surge, or cold
supercapacitor. Exact-image PPK2 HIL remains the acceptance evidence.
"""

from __future__ import annotations

import json


SOURCES = {
    "bq25570": "https://www.ti.com/lit/ds/symlink/bq25570.pdf",
    "max_m10s": (
        "https://content.u-blox.com/sites/default/files/"
        "MAX-M10S_DataSheet_UBX-20035208.pdf"
    ),
    "rak3172": (
        "https://docs.rakwireless.com/product-categories/wisduo/"
        "rak3172-module/datasheet/"
    ),
}

VOUT_SET_V = 3.312
GPS_FLOOR_V = 3.600
TX_FLOOR_V = 3.000

# TI Rev. G table: maximum buck high-side RDS(on) at the lower published
# VSTOR test point. This is intentionally more pessimistic than interpolating
# toward the 2.0 ohm maximum at 4.2 V.
BQ_BUCK_HIGH_SIDE_MAX_OHM = 2.9
BQ_OUTPUT_CURRENT_MIN_A_AT_3V3_TO_1V8 = 0.093
BQ_CYCLE_CURRENT_LIMIT_MIN_A = 0.160

# Exact capacitor: 50 milliohm maximum room ESR. Its -40 C graph is about 1.8x
# room ESR; that multiplier is typical graphical data, not a guaranteed limit.
CAP_ROOM_ESR_MAX_OHM = 0.050
CAP_COLD_ESR_MODEL_OHM = 0.090

GPS_VIO_3V3_MODE_MIN_V = 2.700
GPS_VCC_MIN_V = 1.760
GPS_STARTUP_SURGE_MAX_A = 0.100
RAK3172_VCC_MIN_V = 2.000
LORA_14DBM_MODEL_A = 0.044


def ohmic_drop_v(current_a: float, switch_ohm: float, cap_esr_ohm: float) -> float:
    return current_a * (switch_ohm + cap_esr_ohm)


def audit() -> dict[str, object]:
    gps_drop = ohmic_drop_v(
        GPS_STARTUP_SURGE_MAX_A,
        BQ_BUCK_HIGH_SIDE_MAX_OHM,
        CAP_COLD_ESR_MODEL_OHM,
    )
    tx_drop = ohmic_drop_v(
        LORA_14DBM_MODEL_A,
        BQ_BUCK_HIGH_SIDE_MAX_OHM,
        CAP_COLD_ESR_MODEL_OHM,
    )

    gates = {
        "gps_floor_above_3v3_mode_vio_min_in_ohmic_screen": (
            GPS_FLOOR_V - gps_drop >= GPS_VIO_3V3_MODE_MIN_V
        ),
        "tx_floor_above_rak_vcc_min_in_ohmic_screen": (
            TX_FLOOR_V - tx_drop >= RAK3172_VCC_MIN_V
        ),
        "gps_floor_keeps_buck_fully_regulated_under_pessimistic_ohmic_screen": (
            GPS_FLOOR_V - gps_drop >= VOUT_SET_V
        ),
        "bq_datasheet_guarantees_exact_gps_startup_case": False,
        "exact_final_image_room_low_rail_hil_passed": False,
        "exact_fitted_cap_cold_low_rail_hil_passed": False,
    }
    return {
        "passed": all(gates.values()),
        "status": "BLOCKED_LOW_RAIL_THRESHOLDS_REQUIRE_EXACT_ASSEMBLY_HIL",
        "sources": SOURCES,
        "inputs": {
            "bq_buck_high_side_max_ohm_at_low_test_voltage": BQ_BUCK_HIGH_SIDE_MAX_OHM,
            "bq_output_current_min_a_at_vstor_3v3_vout_1v8": (
                BQ_OUTPUT_CURRENT_MIN_A_AT_3V3_TO_1V8
            ),
            "bq_cycle_current_limit_min_a": BQ_CYCLE_CURRENT_LIMIT_MIN_A,
            "cap_room_esr_max_ohm": CAP_ROOM_ESR_MAX_OHM,
            "cap_cold_esr_typical_graph_model_ohm": CAP_COLD_ESR_MODEL_OHM,
            "gps_startup_surge_max_a": GPS_STARTUP_SURGE_MAX_A,
            "gps_vio_3v3_mode_min_v": GPS_VIO_3V3_MODE_MIN_V,
            "gps_vcc_min_v": GPS_VCC_MIN_V,
            "rak3172_vcc_min_v": RAK3172_VCC_MIN_V,
            "lora_14dbm_current_model_a": LORA_14DBM_MODEL_A,
        },
        "screen": {
            "gps_pessimistic_ohmic_drop_v": gps_drop,
            "gps_floor_screened_vout_v": GPS_FLOOR_V - gps_drop,
            "gps_vio_min_margin_v": (
                GPS_FLOOR_V - gps_drop - GPS_VIO_3V3_MODE_MIN_V
            ),
            "gps_full_regulation_margin_v": GPS_FLOOR_V - gps_drop - VOUT_SET_V,
            "tx_pessimistic_ohmic_drop_v": tx_drop,
            "tx_floor_screened_vout_v": TX_FLOOR_V - tx_drop,
            "tx_rak_vcc_min_margin_v": TX_FLOOR_V - tx_drop - RAK3172_VCC_MIN_V,
        },
        "interpretation": (
            "The present 3.6 V GPS and 3.0 V TX floors clear component minimum "
            "supply voltages in a pessimistic ohmic screen. The GPS floor is "
            "about 11 mV short of keeping the 3.312 V buck output fully "
            "regulated if the low-voltage maximum switch resistance, modeled "
            "cold ESR, and 100 mA startup surge all coincide. TI's 93 mA "
            "minimum output-current point is specified for 3.3-to-1.8 V, not "
            "this case. Therefore neither threshold is a guaranteed transient "
            "bound, and short-pulse capacitance plus wiring add uncertainty."
        ),
        "required_hil": (
            "Sweep PPK2 VSTOR across 4.5, 4.4, 3.6, 3.5, 3.0, and below 3.0 V "
            "on the exact image, capturing source VSTOR, VOUT/VDDA, ADC "
            "telemetry, current, boot/reset counters, GNSS startup/standby, "
            "join, primary +14 dBm TX, and auxiliary suppression. Repeat with "
            "the fitted capacitor at room and cold; set thresholds from the "
            "measured worst case plus explicit margin."
        ),
        "gates": gates,
    }


if __name__ == "__main__":
    result = audit()
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["passed"] else 1)
