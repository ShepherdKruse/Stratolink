#!/usr/bin/env python3
"""Fail-closed audit of the exact dual-cell supercapacitor balance topology."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re

from supercap_charge_ceiling_audit import (
    DEFAULT_PCB,
    REFERENCE_TOP_VALUE_MOHM,
    SAFER_MARGIN_TOP_VALUE_MOHM,
    ROOT,
    SUPERCAP_PART,
    SUPERCAP_CELL_RATED_V,
    footprint_blocks,
    screen_divider_option,
)


CAPXX_DATASHEET = (
    "https://capcomp.de/files/inhalte/4-manufacturer/CAP-XX/"
    "cat1-MINI-CELL-PRISMATIC/datasheets/Dual-Cell-5-5V-temp-40-to-70C/"
    "DMF4B5R5G105M3DTA0_DMF1F-Datasheet-V1_6.pdf"
)
CAPXX_BALANCE_WHITEPAPER = (
    "https://cap-xx-assets.s3.eu-west-2.amazonaws.com/"
    "cap_xx_whitepaper_supercapacitor_cell_balancing_d39dd4559f.pdf"
)
CAPXX_BALANCE_WHITEPAPER_SHA256 = (
    "78c01431cc7f474cf7777dbbbdf8a9ef6e992386719cb3093eb3f33e9fa4a89f"
)
CAPXX_FAQ = "https://cap-xx.com/support/faqs"
TLV8801_DATASHEET = "https://www.ti.com/lit/ds/symlink/tlv8801.pdf"
TLV8801_PART = "TLV8801DBVT"
REFERENCE_RESISTOR_DATASHEET = "https://www.vishay.com/doc?28952="
REFERENCE_RESISTOR_DISTRIBUTOR = (
    "https://www.digikey.com/en/products/detail/vishay/"
    "MCA1206MD1005BP100/11196602"
)
REFERENCE_RESISTOR_PART = "MCA1206MD1005BP100"
ALD910025_DATASHEET = "https://www.aldinc.com/pdf/ALD810025.pdf"
ALD_SAB_CIRCUIT_NOTE = "https://www.aldinc.com/pdf/sabfet_11101.0.pdf"
ALD_SABMB2_DATASHEET = "https://www.aldinc.com/pdf/SABMB2.pdf"
ALD_SAB_FAMILY_DATASHEET = "https://www.aldinc.com/pdf/ALD8100xxFamily.pdf"
ALD910025_PART = "ALD910025SALI"
ALD910025_DISTRIBUTOR = (
    "https://www.digikey.com/en/products/detail/advanced-linear-devices-inc/"
    "ALD910025SALI/5222333"
)
SUPERCAP_DESIGNATOR = "C5"

# AN1002 normally recommends 10 kohm per-cell passive resistors and says the
# highest normally recommended value is 39 kohm at <=50 C. That approach is
# incompatible with this power budget. Its low-current reference instead uses
# a TLV8801, 10 Mohm/10 Mohm reference divider, and 22 ohm midpoint resistor.
PASSIVE_REFERENCE_RESISTOR_OHM = 10_000.0
ACTIVE_REFERENCE_RESISTOR_OHM = 10_000_000.0
ACTIVE_OPAMP_TYPICAL_CURRENT_UA = 0.480
ACTIVE_OPAMP_MAX_CURRENT_UA = 0.700
ACTIVE_MIDPOINT_RESISTOR_OHM = 22.0
ACTIVE_REFERENCE_RESISTOR_TOLERANCE = 0.001
ACTIVE_REFERENCE_RESISTOR_TCR_PPM_C = 25.0
ACTIVE_REFERENCE_TCR_EXCURSION_C = 65.0  # 25 C reference to -40 C limit
ACTIVE_OPAMP_MAX_OFFSET_V = 0.0045
ACTIVE_OPAMP_MIN_SUPPLY_V = 1.7
ACTIVE_OPAMP_MAX_SUPPLY_V = 5.5
ACTIVE_OPAMP_TYPICAL_OUTPUT_CURRENT_MA = 4.7
ACTIVE_OPAMP_MIN_TEMPERATURE_C = -40.0
ACTIVE_OPAMP_MAX_TEMPERATURE_C = 125.0
MIN_CAPACITANCE_F = 0.8
CONSERVATIVE_FLIGHT3_PLATEAU_FLOOR_V = 3.32
SLEEP_UPPER_UA = 35.0
CAP_LEAKAGE_LIMIT_UA = 6.0

# ALD910025 operating characteristics are specified at 25 C. The threshold
# limits and channel offset have limits; the current curve and temperature
# coefficients are typical-only and therefore remain modeling evidence, not a
# qualification screen. The tabulated points below are copied from the exact
# ALD810025/ALD910025 datasheet and interpolated logarithmically.
ALD_TYPICAL_CURRENT_POINTS = (
    (2.10, 0.0001),
    (2.20, 0.001),
    (2.30, 0.01),
    (2.40, 0.1),
    (2.50, 1.0),
    (2.60, 10.0),
    (2.72, 100.0),
    (2.80, 300.0),
    (2.94, 1000.0),
    (3.00, 3000.0),
    (3.50, 10000.0),
)
ALD_THRESHOLD_MIN_V = 2.48
ALD_THRESHOLD_TYPICAL_V = 2.50
ALD_THRESHOLD_MAX_V = 2.52
ALD_CHANNEL_OFFSET_MAX_V = 0.020
ALD_THRESHOLD_TEMPCO_TYPICAL_V_C = -0.0022
ALD_OFFSET_TEMPCO_TYPICAL_V_C = 0.000005
ALD_MIN_TEMPERATURE_C = -40.0
ALD_MAX_TEMPERATURE_C = 85.0
ALD_MAX_OPERATING_CURRENT_MA = 80.0
FLIGHT3_COLDEST_OBSERVED_C = -42.1


def pad_block(footprint: str, number: str) -> str:
    match = re.search(
        rf'\(pad "{re.escape(number)}".*?(?=\n\s*\(pad |\Z)',
        footprint,
        re.DOTALL,
    )
    if not match:
        raise ValueError(f"missing C5 pad {number}")
    return match.group(0)


def constant_current_runtime_h(ceiling_v: float, current_ua: float) -> float:
    return (
        MIN_CAPACITANCE_F
        * (ceiling_v - CONSERVATIVE_FLIGHT3_PLATEAU_FLOOR_V)
        / (current_ua * 1e-6)
        / 3600.0
    )


def ald_typical_current_ua(cell_v: float, threshold_v: float = 2.50) -> float:
    """Log-interpolate ALD's 25 C typical curve after threshold shifting."""
    shifted_v = cell_v - (threshold_v - ALD_THRESHOLD_TYPICAL_V)
    points = ALD_TYPICAL_CURRENT_POINTS
    if shifted_v <= points[0][0]:
        # ALD's circuit note gives approximately one decade per 0.1 V and
        # explicitly says current reaches the pA range below 1.9 V.
        return points[0][1] * 10.0 ** ((shifted_v - points[0][0]) / 0.1)
    if shifted_v >= points[-1][0]:
        return points[-1][1] * 10.0 ** (
            (shifted_v - points[-1][0]) / 0.1
        )
    for (v0, i0), (v1, i1) in zip(points, points[1:]):
        if v0 <= shifted_v <= v1:
            fraction = (shifted_v - v0) / (v1 - v0)
            return 10.0 ** (
                math.log10(i0) + fraction * (math.log10(i1) - math.log10(i0))
            )
    raise AssertionError("unreachable ALD current interpolation")


def ald_typical_threshold_v(temperature_c: float, base_threshold_v: float) -> float:
    return base_threshold_v + ALD_THRESHOLD_TEMPCO_TYPICAL_V_C * (
        temperature_c - 25.0
    )


def ald_modeled_runtime_h(
    ceiling_v: float,
    temperature_c: float,
    base_threshold_v: float = ALD_THRESHOLD_TYPICAL_V,
    steps: int = 50_000,
) -> float:
    """Integrate balanced-stack darkness runtime using typical ALD behavior.

    One identical shunt current flows from each series cell. Its stack-energy
    effect is equivalent to that one channel current (not twice the current).
    """
    threshold_v = ald_typical_threshold_v(temperature_c, base_threshold_v)
    dv = (ceiling_v - CONSERVATIVE_FLIGHT3_PLATEAU_FLOOR_V) / steps
    seconds = 0.0
    for index in range(steps):
        stack_v = CONSERVATIVE_FLIGHT3_PLATEAU_FLOOR_V + (index + 0.5) * dv
        balancing_ua = ald_typical_current_ua(stack_v / 2.0, threshold_v)
        seconds += MIN_CAPACITANCE_F * dv / (
            (SLEEP_UPPER_UA + CAP_LEAKAGE_LIMIT_UA + balancing_ua) * 1e-6
        )
    return seconds / 3600.0


def ald_typical_leakage_equilibrium(
    total_v: float,
    leakage_mismatch_ua: float,
    high_cell_threshold_v: float = ALD_THRESHOLD_TYPICAL_V,
    low_cell_threshold_v: float = ALD_THRESHOLD_TYPICAL_V,
) -> tuple[float, float]:
    """Solve typical high/low cell voltages for a leakage-current mismatch."""
    lower = total_v / 2.0
    upper = min(SUPERCAP_CELL_RATED_V, total_v)
    for _ in range(100):
        high_v = (lower + upper) / 2.0
        low_v = total_v - high_v
        difference_ua = (
            ald_typical_current_ua(high_v, high_cell_threshold_v)
            - ald_typical_current_ua(low_v, low_cell_threshold_v)
        )
        if difference_ua < leakage_mismatch_ua:
            lower = high_v
        else:
            upper = high_v
    high_v = (lower + upper) / 2.0
    return high_v, total_v - high_v


def worst_reference_fraction() -> float:
    """Highest half-supply fraction from independent tolerance and TCR signs."""
    tcr = (
        ACTIVE_REFERENCE_RESISTOR_TCR_PPM_C
        * 1e-6
        * ACTIVE_REFERENCE_TCR_EXCURSION_C
    )
    high = (1.0 + ACTIVE_REFERENCE_RESISTOR_TOLERANCE) * (1.0 + tcr)
    low = (1.0 - ACTIVE_REFERENCE_RESISTOR_TOLERANCE) * (1.0 - tcr)
    return high / (high + low)


def architecture_sensitivity(top_mohm: float) -> dict[str, object]:
    """Compare balancer boundaries at one source-screened divider ratio."""
    divider = screen_divider_option(top_mohm)
    ceiling = float(divider["nominal_ceiling_v"])
    full_upper = float(divider["full_temperature_screening_upper_v"])
    initial_high = float(
        divider["worst_initial_cell_v_at_full_temperature_upper"]
    )
    initial_low = full_upper - initial_high

    tlv_screen_current_ua = (
        SLEEP_UPPER_UA
        + CAP_LEAKAGE_LIMIT_UA
        + ceiling / (2.0 * ACTIVE_REFERENCE_RESISTOR_OHM) * 1e6
        + ACTIVE_OPAMP_MAX_CURRENT_UA
    )
    tlv_cell_upper = (
        full_upper * worst_reference_fraction() + ACTIVE_OPAMP_MAX_OFFSET_V
    )
    tlv_initial_demand_ma = (
        full_upper * 0.02 / ACTIVE_MIDPOINT_RESISTOR_OHM * 1000.0
    )

    ald_initial_high_ua = ald_typical_current_ua(initial_high)
    ald_initial_low_ua = ald_typical_current_ua(initial_low)
    ald_equilibrium_high, ald_equilibrium_low = ald_typical_leakage_equilibrium(
        full_upper,
        CAP_LEAKAGE_LIMIT_UA,
        ALD_THRESHOLD_TYPICAL_V + ALD_CHANNEL_OFFSET_MAX_V,
        ALD_THRESHOLD_TYPICAL_V,
    )

    return {
        "top_mohm": top_mohm,
        "nominal_ceiling_v": divider["nominal_ceiling_v"],
        "full_temperature_screening_upper_v": divider[
            "full_temperature_screening_upper_v"
        ],
        "worst_initial_cell_margin_to_2v75_v": divider[
            "worst_initial_cell_margin_to_2v75_v"
        ],
        "tlv8801": {
            "minimum_cap_screening_runtime_h": round(
                constant_current_runtime_h(ceiling, tlv_screen_current_ua), 3
            ),
            "balanced_cell_margin_to_2v75_v": round(
                SUPERCAP_CELL_RATED_V - tlv_cell_upper, 6
            ),
            "initial_4pct_mismatch_correction_demand_ma": round(
                tlv_initial_demand_ma, 6
            ),
            "demand_minus_typical_output_current_ma": round(
                tlv_initial_demand_ma - ACTIVE_OPAMP_TYPICAL_OUTPUT_CURRENT_MA,
                6,
            ),
            "current_limit_boundary": (
                "TI specifies 4.7 mA only as typical short-circuit current; "
                "no minimum correction-current guarantee is available"
            ),
        },
        "ald910025_typical_only": {
            "minimum_cap_25c_runtime_h_with_min_25c_threshold": round(
                ald_modeled_runtime_h(ceiling, 25.0, ALD_THRESHOLD_MIN_V), 3
            ),
            "initial_high_cell_v": round(initial_high, 6),
            "initial_low_cell_v": round(initial_low, 6),
            "initial_net_equalizing_current_ua": round(
                ald_initial_high_ua - ald_initial_low_ua, 6
            ),
            "full_screen_6ua_mismatch_equilibrium_high_cell_v": round(
                ald_equilibrium_high, 6
            ),
            "full_screen_6ua_mismatch_equilibrium_low_cell_v": round(
                ald_equilibrium_low, 6
            ),
            "full_screen_6ua_mismatch_equilibrium_margin_to_2v75_v": round(
                SUPERCAP_CELL_RATED_V - ald_equilibrium_high, 6
            ),
            "boundary": (
                "current curve and temperature coefficients are typical-only; "
                "these values rank candidates but cannot qualify correction time"
            ),
        },
    }


def audit(root: Path = ROOT) -> dict[str, object]:
    pcb_path = root / DEFAULT_PCB.relative_to(ROOT)
    footprints = footprint_blocks(pcb_path.read_text(encoding="utf-8"))
    if SUPERCAP_DESIGNATOR not in footprints:
        raise ValueError("missing C5 footprint")
    c5 = footprints[SUPERCAP_DESIGNATOR]
    if f'(footprint "lib:{SUPERCAP_PART}"' not in c5:
        raise ValueError("C5 exact part/footprint drift")

    pads = {number: pad_block(c5, number) for number in ("1", "2", "3")}
    if '"Net-(U1-VBAT)"' not in pads["1"]:
        raise ValueError("C5 positive terminal is not on VBAT")
    if '"GND"' not in pads["2"]:
        raise ValueError("C5 negative terminal is not on GND")
    balance_connected = "(net " in pads["3"]

    # Keep the detailed architecture comparison on its original 7.50 Mohm
    # numerical reference. Divider selection is an independent open decision;
    # see supercap_charge_ceiling_audit.py for the 7.32 Mohm safer-margin
    # candidate and the full tradeoff screen.
    candidate = screen_divider_option(REFERENCE_TOP_VALUE_MOHM)
    ceiling = float(candidate["nominal_ceiling_v"])
    passive_balance_current_ua = (
        ceiling / (2.0 * PASSIVE_REFERENCE_RESISTOR_OHM) * 1e6
    )
    active_reference_overhead_ua = (
        ceiling / (2.0 * ACTIVE_REFERENCE_RESISTOR_OHM) * 1e6
        + ACTIVE_OPAMP_TYPICAL_CURRENT_UA
    )
    active_reference_screening_overhead_ua = (
        ceiling / (2.0 * ACTIVE_REFERENCE_RESISTOR_OHM) * 1e6
        + ACTIVE_OPAMP_MAX_CURRENT_UA
    )
    active_pessimistic_current_ua = (
        SLEEP_UPPER_UA + CAP_LEAKAGE_LIMIT_UA + active_reference_overhead_ua
    )
    active_screening_current_ua = (
        SLEEP_UPPER_UA
        + CAP_LEAKAGE_LIMIT_UA
        + active_reference_screening_overhead_ua
    )
    full_upper_v = float(candidate["full_temperature_screening_upper_v"])
    balanced_cell_upper_v = (
        full_upper_v * worst_reference_fraction() + ACTIVE_OPAMP_MAX_OFFSET_V
    )
    initial_correction_demand_ma = (
        full_upper_v * 0.02 / ACTIVE_MIDPOINT_RESISTOR_OHM * 1000.0
    )
    ald_nominal_balanced_cell_v = ceiling / 2.0
    ald_full_upper_balanced_cell_v = full_upper_v / 2.0
    ald_worst_initial_high_cell_v = float(
        candidate["worst_initial_cell_v_at_full_temperature_upper"]
    )
    ald_worst_initial_low_cell_v = full_upper_v - ald_worst_initial_high_cell_v
    ald_initial_high_current_ua = ald_typical_current_ua(
        ald_worst_initial_high_cell_v
    )
    ald_initial_low_current_ua = ald_typical_current_ua(
        ald_worst_initial_low_cell_v
    )
    ald_25c_min_threshold_runtime_h = ald_modeled_runtime_h(
        ceiling, 25.0, ALD_THRESHOLD_MIN_V
    )
    ald_85c_typical_tempco_runtime_h = ald_modeled_runtime_h(
        ceiling, 85.0, ALD_THRESHOLD_MIN_V
    )
    ald_offset_balanced_cell_upper_v = (
        full_upper_v + ALD_CHANNEL_OFFSET_MAX_V
    ) / 2.0
    ald_nominal_leakage_high_v, ald_nominal_leakage_low_v = (
        ald_typical_leakage_equilibrium(
            ceiling,
            CAP_LEAKAGE_LIMIT_UA,
            ALD_THRESHOLD_TYPICAL_V + ALD_CHANNEL_OFFSET_MAX_V,
            ALD_THRESHOLD_TYPICAL_V,
        )
    )
    ald_full_leakage_high_v, ald_full_leakage_low_v = (
        ald_typical_leakage_equilibrium(
            full_upper_v,
            CAP_LEAKAGE_LIMIT_UA,
            ALD_THRESHOLD_TYPICAL_V + ALD_CHANNEL_OFFSET_MAX_V,
            ALD_THRESHOLD_TYPICAL_V,
        )
    )

    gates = {
        "exact_three_terminal_dual_cell_part_bound": True,
        "positive_and_negative_terminals_connected": True,
        "balance_terminal_connected_to_a_balance_network": balance_connected,
        "manufacturer_balance_requirement_resolved_for_exact_application": False,
        "initial_mismatch_correction_current_has_specified_minimum_margin": False,
        "individual_cell_leakage_characterized_against_selected_balancer": False,
        "active_balancer_flight_temperature_envelope_qualified": False,
        "active_balancer_reverse_discharge_transient_path_qualified": False,
        "active_balancer_exact_part_procured_and_verified": False,
        "cell_midpoint_charge_discharge_temperature_hil_passed": False,
    }
    return {
        "passed": all(gates.values()),
        "status": (
            "QUALIFIED" if all(gates.values()) else
            "BLOCKED_UNCONNECTED_SUPERCAP_BALANCE_TERMINAL"
        ),
        "scope": (
            "exact PCB topology plus manufacturer requirement audit; not a "
            "balancer design, divider selection, or cell-mismatch qualification"
        ),
        "sources": {
            "exact_capacitor_datasheet": CAPXX_DATASHEET,
            "manufacturer_balance_whitepaper": CAPXX_BALANCE_WHITEPAPER,
            "manufacturer_balance_whitepaper_sha256": CAPXX_BALANCE_WHITEPAPER_SHA256,
            "manufacturer_faq": CAPXX_FAQ,
            "opamp_datasheet": TLV8801_DATASHEET,
            "reference_resistor_datasheet": REFERENCE_RESISTOR_DATASHEET,
            "reference_resistor_distributor_listing": REFERENCE_RESISTOR_DISTRIBUTOR,
            "ald910025_datasheet": ALD910025_DATASHEET,
            "ald_sab_circuit_note": ALD_SAB_CIRCUIT_NOTE,
            "ald_sabmb2_reference_board_datasheet": ALD_SABMB2_DATASHEET,
            "ald_sab_family_datasheet": ALD_SAB_FAMILY_DATASHEET,
            "ald910025_distributor_listing": ALD910025_DISTRIBUTOR,
        },
        "exact_topology": {
            "part": SUPERCAP_PART,
            "configuration": "dual_cell_three_terminal_positive_negative_balance",
            "positive_pad_net": "Net-(U1-VBAT)",
            "negative_pad_net": "GND",
            "balance_pad_net": None if not balance_connected else "connected",
            "pcb_path": str(pcb_path.resolve()),
        },
        "manufacturer_boundary": (
            "CAP-XX says it elected not to add internal balancing and highly "
            "recommends some form of cell balancing for any series-connected "
            "module; the optimum passive or active solution is application-specific"
        ),
        "passive_reference_rejected_for_energy": {
            "basis": "AN1002 normal 10 kohm per-cell recommendation",
            "candidate_total_ceiling_v": ceiling,
            "added_current_ua": round(passive_balance_current_ua, 6),
            "minimum_cap_baseline_runtime_h_at_35_plus_6_plus_passive_ua": round(
                constant_current_runtime_h(
                    ceiling,
                    SLEEP_UPPER_UA + CAP_LEAKAGE_LIMIT_UA + passive_balance_current_ua,
                ),
                3,
            ),
        },
        "active_tlv8801_reference_not_yet_designed_or_qualified": {
            "opamp_candidate": TLV8801_PART,
            "opamp_package": "SOT-23-5_DBV_2.90mm_x_1.60mm_body",
            "opamp_operating_temperature_c": [
                ACTIVE_OPAMP_MIN_TEMPERATURE_C,
                ACTIVE_OPAMP_MAX_TEMPERATURE_C,
            ],
            "opamp_supply_range_v": [
                ACTIVE_OPAMP_MIN_SUPPLY_V,
                ACTIVE_OPAMP_MAX_SUPPLY_V,
            ],
            "reference_resistor_candidate_each": REFERENCE_RESISTOR_PART,
            "reference_divider_ohm_each": ACTIVE_REFERENCE_RESISTOR_OHM,
            "reference_resistor_tolerance_fraction": (
                ACTIVE_REFERENCE_RESISTOR_TOLERANCE
            ),
            "reference_resistor_tcr_ppm_c": ACTIVE_REFERENCE_RESISTOR_TCR_PPM_C,
            "midpoint_output_resistor_ohm": ACTIVE_MIDPOINT_RESISTOR_OHM,
            "typical_opamp_current_ua": ACTIVE_OPAMP_TYPICAL_CURRENT_UA,
            "datasheet_max_opamp_current_ua": ACTIVE_OPAMP_MAX_CURRENT_UA,
            "modeled_circuit_overhead_ua_excluding_cap_leakage": round(
                active_reference_overhead_ua, 6
            ),
            "screening_circuit_overhead_ua_excluding_cap_leakage": round(
                active_reference_screening_overhead_ua, 6
            ),
            "minimum_cap_baseline_runtime_h_at_35_plus_6_plus_active_overhead_ua": round(
                constant_current_runtime_h(ceiling, active_pessimistic_current_ua), 3
            ),
            "minimum_cap_screening_runtime_h_at_35_plus_6_plus_active_overhead_ua": round(
                constant_current_runtime_h(ceiling, active_screening_current_ua), 3
            ),
            "worst_reference_fraction_with_tolerance_and_tcr": round(
                worst_reference_fraction(), 9
            ),
            "balanced_cell_upper_v_including_max_opamp_offset": round(
                balanced_cell_upper_v, 6
            ),
            "balanced_cell_margin_to_2v75_v": round(
                SUPERCAP_CELL_RATED_V - balanced_cell_upper_v, 6
            ),
            "initial_4pct_mismatch_correction_demand_ma_at_full_upper": round(
                initial_correction_demand_ma, 6
            ),
            "opamp_typical_output_current_ma": (
                ACTIVE_OPAMP_TYPICAL_OUTPUT_CURRENT_MA
            ),
            "output_current_boundary": (
                "the modeled initial correction demand exceeds TI's typical "
                "4.7 mA short-circuit current, for which no minimum is specified; "
                "startup, current saturation, correction time, and stability must "
                "be measured on the exact assembly"
            ),
            "common_mode_boundary": (
                "the half-supply input is within the V- to V+-0.9 V specified "
                "range at the conservative 3.32 V reported-plateau floor and "
                "above; CAP-XX's stated "
                "1.8 V balancer startup point is below the flight floor"
            ),
            "manufacturer_bench_context": (
                "AN1002 reports about 4 uA total including capacitor leakage "
                "after 28 h and 1.5 uA after one week on a different HW207 at "
                "5.5 V/23 C"
            ),
        },
        "active_ald910025_sab_not_yet_designed_or_qualified": {
            "part": ALD910025_PART,
            "package": "SOIC-8_SAL_industrial",
            "purpose": "dual_cell_supercapacitor_auto_balancing_mosfet_array",
            "operating_temperature_c": [
                ALD_MIN_TEMPERATURE_C,
                ALD_MAX_TEMPERATURE_C,
            ],
            "flight3_coldest_observed_c": FLIGHT3_COLDEST_OBSERVED_C,
            "cold_rating_margin_c": round(
                FLIGHT3_COLDEST_OBSERVED_C - ALD_MIN_TEMPERATURE_C, 3
            ),
            "threshold_v_at_1ua_25c": {
                "minimum": ALD_THRESHOLD_MIN_V,
                "typical": ALD_THRESHOLD_TYPICAL_V,
                "maximum": ALD_THRESHOLD_MAX_V,
            },
            "maximum_channel_offset_v_at_25c": ALD_CHANNEL_OFFSET_MAX_V,
            "typical_threshold_tempco_mv_c": (
                ALD_THRESHOLD_TEMPCO_TYPICAL_V_C * 1000.0
            ),
            "typical_offset_tempco_uv_c": (
                ALD_OFFSET_TEMPCO_TYPICAL_V_C * 1e6
            ),
            "absolute_max_operating_current_ma": ALD_MAX_OPERATING_CURRENT_MA,
            "nominal_balanced_cell_v": round(ald_nominal_balanced_cell_v, 6),
            "typical_25c_current_per_cell_ua_at_nominal_balance": round(
                ald_typical_current_ua(ald_nominal_balanced_cell_v), 6
            ),
            "full_screen_balanced_cell_v": round(
                ald_full_upper_balanced_cell_v, 6
            ),
            "typical_25c_current_per_cell_ua_at_full_screen_balance": round(
                ald_typical_current_ua(ald_full_upper_balanced_cell_v), 6
            ),
            "balanced_cell_upper_v_from_25c_max_channel_offset": round(
                ald_offset_balanced_cell_upper_v, 6
            ),
            "balanced_cell_margin_to_2v75_v_at_25c_max_channel_offset": round(
                SUPERCAP_CELL_RATED_V - ald_offset_balanced_cell_upper_v, 6
            ),
            "worst_initial_4pct_cells_at_full_upper": {
                "high_cell_v": round(ald_worst_initial_high_cell_v, 6),
                "low_cell_v": round(ald_worst_initial_low_cell_v, 6),
                "typical_25c_high_channel_current_ua": round(
                    ald_initial_high_current_ua, 6
                ),
                "typical_25c_low_channel_current_ua": round(
                    ald_initial_low_current_ua, 6
                ),
                "typical_25c_net_equalizing_current_ua": round(
                    ald_initial_high_current_ua - ald_initial_low_current_ua, 6
                ),
            },
            "typical_25c_6ua_leakage_mismatch_equilibrium_with_20mv_offset": {
                "nominal_total_v": round(ceiling, 6),
                "nominal_high_cell_v": round(ald_nominal_leakage_high_v, 6),
                "nominal_low_cell_v": round(ald_nominal_leakage_low_v, 6),
                "full_screen_total_v": round(full_upper_v, 6),
                "full_screen_high_cell_v": round(ald_full_leakage_high_v, 6),
                "full_screen_low_cell_v": round(ald_full_leakage_low_v, 6),
                "full_screen_high_cell_margin_to_2v75_v": round(
                    SUPERCAP_CELL_RATED_V - ald_full_leakage_high_v, 6
                ),
            },
            "minimum_cap_modeled_darkness_runtime_h": {
                "25c_with_25c_min_threshold": round(
                    ald_25c_min_threshold_runtime_h, 3
                ),
                "85c_with_typical_tempco_and_25c_min_threshold": round(
                    ald_85c_typical_tempco_runtime_h, 3
                ),
            },
            "energy_model_boundary": (
                "runtime integrates ALD's typical current curve; the current "
                "curve and threshold temperature coefficient have no stated "
                "limits and therefore cannot establish a worst-case budget"
            ),
            "correction_boundary": (
                "the 25 C initial-mismatch currents are typical only. The 80 mA "
                "operating-current rating is an absolute maximum, not guaranteed "
                "sink capability. Prove correction time against the exact solar "
                "charge ramp, capacitance, leakage mismatch, and temperature"
            ),
            "manufacturer_selection_boundary": (
                "ALD requires selecting a maximum leakage-current limit, "
                "testing each capacitor against it before stacking, mapping "
                "that current to an acceptable cell voltage, and checking "
                "tolerance/temperature margin. The 6 uA equilibrium above is "
                "typical-curve sensitivity analysis, not a substitute for "
                "individual-cell leakage characterization"
            ),
            "architecture_advantage": (
                "no always-on reference divider or op-amp; below threshold each "
                "channel falls toward pA current, which is attractive for darkness"
            ),
            "reference_board_boundary": (
                "ALD's SABMB2 is 25.4 mm by 15.24 mm and is a development/"
                "prototype reference, not flight geometry. It adds optional "
                "TO277 Schottky clamps because fast capacitor discharge can "
                "reverse-bias internal nodes above the 80 mA per-channel limit. "
                "A custom interposer must either include qualified clamps or "
                "prove the exact GPS/radio/brownout transients stay within limit"
            ),
            "procurement_boundary": (
                "the inspected Mouser exact-part page showed zero stock and a "
                "future replenishment; distributor snapshots conflict. Procure "
                "and verify the exact industrial SALI suffix before selecting "
                "this path"
            ),
            "qualification_boundary": (
                "industrial SALI operation stops at -40 C, 2.1 C warmer than the "
                "coldest Flight-3 telemetry. Exact-part source availability, "
                "temperature margin, PCB/flex layout, cell-voltage HIL, and "
                "measured darkness energy remain open"
            ),
            "custom_cold_screening_path": (
                "ALD's family datasheet says custom M-suffix versions are "
                "available for -55 C to 125 C. No exact ALD910025 ordering "
                "code, electrical limits, price, lead time, or delivered lot "
                "is bound here; obtain a manufacturer quote and certificate. "
                "This would cover only the balancer, not the -40 C capacitor"
            ),
        },
        "cell_match_screen": {
            "manufacturer_matching": "+/-4% between the two cells",
            "cell_rated_v": SUPERCAP_CELL_RATED_V,
            "reference_7v50_divider_full_upper_v": candidate[
                "full_temperature_screening_upper_v"
            ],
            "worst_initial_cell_v": candidate[
                "worst_initial_cell_v_at_full_temperature_upper"
            ],
            "margin_v": candidate["worst_initial_cell_margin_to_2v75_v"],
            "passed": candidate["initial_cell_match_screen_below_2v75"],
        },
        "divider_architecture_sensitivity": {
            "scope": (
                "common balancer comparison across divider ratios; 7.50 Mohm "
                "is the historical reference, 7.32 Mohm is the safer-margin "
                "prototype candidate, and 7.15 Mohm is an unbound ratio option"
            ),
            "options": [
                architecture_sensitivity(value)
                for value in (
                    REFERENCE_TOP_VALUE_MOHM,
                    SAFER_MARGIN_TOP_VALUE_MOHM,
                    7.15,
                )
            ],
        },
        "required_resolution": (
            "Before C5 installation, review both the CAP-XX AN1002 TLV8801 "
            "reference and the purpose-built ALD910025SALI dual SAB MOSFET with "
            "CAP-XX for this exact DMF energy-harvesting duty cycle. Select and "
            "lay out a qualified low-leakage daughterboard or flex using pad 3; "
            "neither path has guaranteed initial-correction and cold margin. "
            "For the ALD path, resolve its optional reverse-discharge clamps "
            "and procure the exact SALI suffix. "
            "Then independently "
            "capture total voltage and "
            "both cell voltages during controlled charge, dark discharge, load "
            "steps, temperature sweep, and recovery. No cell may exceed its "
            "manufacturer limit. Re-run the darkness budget with measured "
            "balancer current."
        ),
        "gates": gates,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--allow-blocked", action="store_true")
    args = parser.parse_args()
    result = audit()
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        if args.output.exists():
            raise SystemExit(f"refusing to overwrite balance evidence: {args.output}")
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    if not result["passed"] and not args.allow_blocked:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
