#!/usr/bin/env python3
"""Screen the exact BQ25570/supercap charge ceiling against absolute maximums.

This is a source-bound tolerance screen, not a substitute for measuring the
finished assembly over light, temperature, and load.  The BQ25570 datasheet's
overall +/-2% threshold guarantee is explicitly conditioned on 0.1% divider
resistors, while the production BOM selects 1% parts.  TI's own EVM guide,
however, publishes min/max thresholds that explicitly combine +/-2% set-point
accuracy with +/-1% resistor tolerance.  We use that TI-supported worst-case
design method, add independent resistor TCR drift, and fail closed if the
result reaches either 5.5 V absolute maximum.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
from typing import Optional


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DEFAULT_BOM = ROOT / "hardware/gerbers/production_files/BOM-stratolink.csv"
DEFAULT_PCB = ROOT / "hardware/pcb/stratolink.kicad_pcb"
DEFAULT_FLIGHT_POWER = ROOT / "analysis/power/flight_power.csv"

TI_DATASHEET = "https://www.ti.com/lit/ds/symlink/bq25570.pdf"
TI_EVM_GUIDE = "https://www.ti.com/lit/ug/sluuaa7a/sluuaa7a.pdf"
CAPXX_DATASHEET = (
    "https://capcomp.de/files/inhalte/4-manufacturer/CAP-XX/"
    "cat1-MINI-CELL-PRISMATIC/datasheets/Dual-Cell-5-5V-temp-40-to-70C/"
    "DMF4B5R5G105M3DTA0_DMF1F-Datasheet-V1_6.pdf"
)
R1_SOURCE = "https://www.lcsc.com/product-detail/C423131.html"
R2_SOURCE = "https://www.lcsc.com/product-detail/C2091474.html"
REFERENCE_TOP_SOURCE = "https://www.vishay.com/docs/20035/dcrcwe3.pdf"
REFERENCE_TOP_LISTING = (
    "https://www.lcsc.com/product-detail/"
    "Chip-Resistor-Surface-Mount_Vishay-Intertech-"
    "CRCW04027M50FKED_C1854640.html"
)

CHARGER_DESIGNATOR = "U1"
CHARGER_PART = "BQ25570RGRR"
CHARGER_LCSC = "C506250"
SUPERCAP_DESIGNATOR = "C5"
SUPERCAP_PART = "DMF4B5R5G105M3DTA0"
TOP_DESIGNATOR = "R1"
TOP_VALUE_MOHM = 8.25
TOP_LCSC = "C423131"
TOP_PART = "0402WGF8254TCE"
BOTTOM_DESIGNATOR = "R2"
BOTTOM_VALUE_MOHM = 4.22
BOTTOM_LCSC = "C2091474"
BOTTOM_PART = "CRCW04024M22FKED"

VBIAS_TYP_V = 1.21
DIVIDER_TOLERANCE = 0.01
DIVIDER_TCR_PPM_PER_C = 100.0
DIVIDER_REFERENCE_TEMP_C = 25.0
BQ25570_OPERATING_MIN_C = -40.0
BQ25570_OPERATING_MAX_C = 85.0
DATASHEET_QUALIFYING_TOLERANCE = 0.001
THRESHOLD_ACCURACY = 0.02
ABSOLUTE_MAX_V = 5.5
RECOMMENDED_DIVIDER_SUM_MIN_MOHM = 11.0
RECOMMENDED_DIVIDER_SUM_NOMINAL_MOHM = 13.0
RECOMMENDED_DIVIDER_SUM_MAX_MOHM = 15.0
SUPERCAP_NOMINAL_CAPACITANCE_F = 1.0
SUPERCAP_MIN_CAPACITANCE_F = 0.8
SUPERCAP_MAX_CAPACITANCE_F = 1.2
SUPERCAP_ESR_MAX_MOHM = 50.0
SUPERCAP_OPERATING_MIN_C = -40.0
SUPERCAP_OPERATING_MAX_C = 70.0
# The flown fixed-VDDA ADC loses VSTOR observability in buck dropout; 3.32 V is
# the minimum reported plateau, not measured BOR. Retain it only as a
# deliberately conservative energy-accounting endpoint. See
# flight3_vstor_floor_audit.py.
CONSERVATIVE_FLIGHT3_PLATEAU_FLOOR_V = 3.32

# Ratio alternatives only. TI's EVM guide supports combining +/-2% set-point
# error with +/-1% divider tolerances as a design screen, but these values are
# not approved part substitutions. Exact part identity, TCR, voltage
# coefficient, solder/flux leakage, fitted threshold, capacitance, ESR,
# temperature, and load HIL remain unresolved.
SCREENING_TOP_OPTIONS_MOHM = (8.06, 7.87, 7.68, 7.50, 7.32, 7.15)
# Keep the 7.50 Mohm architecture as a stable numerical reference because the
# detailed balancer model was originally built around it.  It is not an
# approved or "preferred" BOM choice: its worst initial cell screen has only
# 19 mV of headroom.
REFERENCE_TOP_VALUE_MOHM = 7.50
REFERENCE_TOP_PART = "CRCW04027M50FKED"
# 7.32 Mohm is a safer-margin prototype candidate only.  It gains 42.44 mV of
# initial cell headroom over the 7.50 Mohm reference while sacrificing about
# 0.41 h in the simple 0.8 F / 41 uA darkness boundary model.  CAP-XX review,
# fitted threshold metrology, and complete assembly HIL remain mandatory.
SAFER_MARGIN_TOP_VALUE_MOHM = 7.32
SAFER_MARGIN_TOP_PART = "CRCW04027M32FKED"
SAFER_MARGIN_TOP_ALTERNATE_PART = "RC0402FR-077M32L"
SAFER_MARGIN_TOP_LISTING = (
    "https://www.digikey.com/en/products/filter/"
    "chip-resistor-surface-mount/7-32-mohms/52"
)
SUPERCAP_CELL_RATED_V = 2.75
SUPERCAP_DUAL_CELL_MATCH_FRACTION = 0.04


def designators(raw: str) -> set[str]:
    return {item.strip() for item in raw.split(",") if item.strip()}


def bom_row(rows: list[dict[str, str]], designator: str) -> dict[str, str]:
    matches = [row for row in rows if designator in designators(row["Designator"])]
    if len(matches) != 1:
        raise ValueError(f"expected one BOM row for {designator}, got {len(matches)}")
    return matches[0]


def footprint_blocks(text: str) -> dict[str, str]:
    """Return PCB footprint S-expressions keyed by reference."""
    blocks: dict[str, str] = {}
    cursor = 0
    while True:
        start = text.find("\n\t(footprint ", cursor)
        if start < 0:
            break
        start += 1
        depth = 0
        in_string = False
        escaped = False
        end = None
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
        if end is None:
            raise ValueError("unterminated PCB footprint")
        block = text[start:end]
        match = re.search(r'\(property "Reference" "([^"]+)"', block)
        if match:
            reference = match.group(1)
            if reference in blocks:
                raise ValueError(f"duplicate PCB footprint reference {reference}")
            blocks[reference] = block
        cursor = end
    return blocks


def require_patterns(block: str, reference: str, patterns: tuple[str, ...]) -> None:
    for pattern in patterns:
        if not re.search(pattern, block, re.DOTALL):
            raise ValueError(f"{reference} PCB topology/property drift: {pattern}")


def ceiling_v(
    top_mohm: float,
    bottom_mohm: float,
    resistor_tolerance: float = 0.0,
    threshold_error: float = 0.0,
    tcr_ppm_per_c: float = 0.0,
    temperature_delta_c: float = 0.0,
) -> float:
    """Upper VBAT_OV from TI equation 2 and independent ratio extremes."""
    thermal_fraction = tcr_ppm_per_c * 1e-6 * temperature_delta_c
    top = top_mohm * (1.0 + resistor_tolerance) * (1.0 + thermal_fraction)
    bottom = bottom_mohm * (1.0 - resistor_tolerance) * (1.0 - thermal_fraction)
    nominal_reference = 1.5 * VBIAS_TYP_V
    return nominal_reference * (1.0 + top / bottom) * (1.0 + threshold_error)


def stored_energy_j(capacitance_f: float, ceiling: float, floor: float) -> float:
    if capacitance_f <= 0.0 or ceiling <= floor:
        raise ValueError("invalid capacitor energy bounds")
    return 0.5 * capacitance_f * (ceiling**2 - floor**2)


def screen_divider_option(top_mohm: float) -> dict[str, float | bool]:
    nominal = ceiling_v(top_mohm, BOTTOM_VALUE_MOHM)
    full_temperature_upper = ceiling_v(
        top_mohm,
        BOTTOM_VALUE_MOHM,
        DIVIDER_TOLERANCE,
        THRESHOLD_ACCURACY,
        DIVIDER_TCR_PPM_PER_C,
        max(
            abs(BQ25570_OPERATING_MIN_C - DIVIDER_REFERENCE_TEMP_C),
            abs(BQ25570_OPERATING_MAX_C - DIVIDER_REFERENCE_TEMP_C),
        ),
    )
    # CAP-XX AN1002 says its two cells are capacitance-matched within +/-4%.
    # At the edge, initial charge division puts 52% of total voltage on the
    # lower-capacitance cell before the balance circuit corrects it.
    worst_initial_cell_v = full_temperature_upper * (
        1.0 + SUPERCAP_DUAL_CELL_MATCH_FRACTION
    ) / 2.0
    return {
        "top_mohm": top_mohm,
        "bottom_mohm": BOTTOM_VALUE_MOHM,
        "divider_sum_mohm": round(top_mohm + BOTTOM_VALUE_MOHM, 6),
        "nominal_ceiling_v": round(nominal, 6),
        "full_temperature_screening_upper_v": round(full_temperature_upper, 6),
        "full_temperature_screening_margin_to_5v5_v": round(
            ABSOLUTE_MAX_V - full_temperature_upper, 6
        ),
        "screening_upper_below_5v5": full_temperature_upper < ABSOLUTE_MAX_V,
        "worst_initial_cell_v_at_full_temperature_upper": round(
            worst_initial_cell_v, 6
        ),
        "worst_initial_cell_margin_to_2v75_v": round(
            SUPERCAP_CELL_RATED_V - worst_initial_cell_v, 6
        ),
        "initial_cell_match_screen_below_2v75": (
            worst_initial_cell_v < SUPERCAP_CELL_RATED_V
        ),
        "nominal_energy_to_3v32_at_1F_j": round(
            stored_energy_j(
                SUPERCAP_NOMINAL_CAPACITANCE_F,
                nominal,
                CONSERVATIVE_FLIGHT3_PLATEAU_FLOOR_V,
            ),
            6,
        ),
        "minimum_energy_to_3v32_at_0v8F_j": round(
            stored_energy_j(
                SUPERCAP_MIN_CAPACITANCE_F,
                nominal,
                CONSERVATIVE_FLIGHT3_PLATEAU_FLOOR_V,
            ),
            6,
        ),
    }


def historical_power(path: Path) -> dict[str, object]:
    observations: list[dict[str, str]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            try:
                voltage = float(row["battery_voltage"])
            except (KeyError, TypeError, ValueError):
                continue
            row = dict(row)
            row["_voltage"] = str(voltage)
            observations.append(row)
    if not observations:
        raise ValueError("flight power file has no numeric battery_voltage rows")
    maximum = max(float(row["_voltage"]) for row in observations)
    maxima = [row for row in observations if float(row["_voltage"]) == maximum]
    return {
        "numeric_rows": len(observations),
        "maximum_v": maximum,
        "maximum_margin_to_5v5_v": ABSOLUTE_MAX_V - maximum,
        "first_maximum_utc": maxima[0]["time"],
        "maximum_row_count": len(maxima),
    }


def exact_payload_observation(path: Path) -> dict[str, object]:
    observations: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            try:
                row = json.loads(line)
                if row.get("event") != "ttn_uplink":
                    continue
                telemetry = row["telemetry"]
                voltage = float(telemetry["vstor_mv"]) / 1000.0
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"invalid TTN telemetry at {path}:{line_number}: {exc}"
                ) from exc
            observations.append(
                {
                    "vstor_v": voltage,
                    "f_cnt": int(row["f_cnt"]),
                    "received_at": row["received_at"],
                    "solar_mv": int(telemetry["solar_mv"]),
                    "ambient_lux": int(telemetry["ambient_lux"]),
                }
            )
    if not observations:
        raise ValueError("exact-payload TTN log has no telemetry rows")
    maximum = max(observations, key=lambda row: float(row["vstor_v"]))
    raw = path.read_bytes()
    return {
        "scope": (
            "telemetry ADC observation on the exact payload without C5; not a "
            "calibrated threshold, transient capture, or fitted-supercap test"
        ),
        "rows": len(observations),
        "maximum_v": maximum["vstor_v"],
        "maximum_margin_to_5v5_v": ABSOLUTE_MAX_V - float(maximum["vstor_v"]),
        "maximum_f_cnt": maximum["f_cnt"],
        "maximum_received_at": maximum["received_at"],
        "maximum_solar_mv": maximum["solar_mv"],
        "maximum_ambient_lux": maximum["ambient_lux"],
        "provenance": {
            "path": str(path.resolve()),
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        },
    }


def audit(root: Path = ROOT, ttn_path: Optional[Path] = None) -> dict[str, object]:
    bom_path = root / DEFAULT_BOM.relative_to(ROOT)
    pcb_path = root / DEFAULT_PCB.relative_to(ROOT)
    power_path = root / DEFAULT_FLIGHT_POWER.relative_to(ROOT)

    with bom_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    r1 = bom_row(rows, TOP_DESIGNATOR)
    r2 = bom_row(rows, BOTTOM_DESIGNATOR)
    charger = bom_row(rows, CHARGER_DESIGNATOR)
    supercap = bom_row(rows, SUPERCAP_DESIGNATOR)

    expected_bom = {
        TOP_DESIGNATOR: ("8.25MΩ", TOP_LCSC),
        BOTTOM_DESIGNATOR: ("4.22MΩ", BOTTOM_LCSC),
        CHARGER_DESIGNATOR: ("~", CHARGER_LCSC),
        SUPERCAP_DESIGNATOR: ("1F", ""),
    }
    actual_rows = {
        TOP_DESIGNATOR: r1,
        BOTTOM_DESIGNATOR: r2,
        CHARGER_DESIGNATOR: charger,
        SUPERCAP_DESIGNATOR: supercap,
    }
    for reference, (comment, lcsc) in expected_bom.items():
        row = actual_rows[reference]
        if row["Comment"] != comment or row["LCSC"] != lcsc:
            raise ValueError(
                f"{reference} BOM drift: expected {(comment, lcsc)}, "
                f"got {(row['Comment'], row['LCSC'])}"
            )
    if supercap["Footprint"] != SUPERCAP_PART:
        raise ValueError(f"C5 supercap part drift: {supercap['Footprint']}")

    blocks = footprint_blocks(pcb_path.read_text(encoding="utf-8"))
    for reference in (TOP_DESIGNATOR, BOTTOM_DESIGNATOR, CHARGER_DESIGNATOR, SUPERCAP_DESIGNATOR):
        if reference not in blocks:
            raise ValueError(f"missing PCB footprint {reference}")
    require_patterns(
        blocks[TOP_DESIGNATOR],
        TOP_DESIGNATOR,
        (
            r'\(property "Value" "8\.25MΩ"',
            r'\(pad "1".*?\(net \d+ "Net-\(U1-VRDIV\)"\)',
            r'\(pad "2".*?\(net \d+ "Net-\(U1-VBAT_OV\)"\)',
        ),
    )
    require_patterns(
        blocks[BOTTOM_DESIGNATOR],
        BOTTOM_DESIGNATOR,
        (
            r'\(property "Value" "4\.22MΩ"',
            r'\(pad "1".*?\(net \d+ "Net-\(U1-VBAT_OV\)"\)',
            r'\(pad "2".*?\(net \d+ "GND"\)',
        ),
    )
    require_patterns(
        blocks[CHARGER_DESIGNATOR],
        CHARGER_DESIGNATOR,
        (
            rf'\(property "Manufacturer Part" "{CHARGER_PART}"',
            rf'\(property "Supplier Part" "{CHARGER_LCSC}"',
            r'\(pad "7".*?\(net \d+ "Net-\(U1-VBAT_OV\)"\).*?\(pinfunction "VBAT_OV"\)',
            r'\(pad "8".*?\(net \d+ "Net-\(U1-VRDIV\)"\).*?\(pinfunction "VRDIV"\)',
            r'\(pad "18".*?\(net \d+ "Net-\(U1-VBAT\)"\).*?\(pinfunction "VBAT"\)',
        ),
    )
    require_patterns(
        blocks[SUPERCAP_DESIGNATOR],
        SUPERCAP_DESIGNATOR,
        (
            rf'\(footprint "lib:{SUPERCAP_PART}"',
            r'\(pad "1".*?\(net \d+ "Net-\(U1-VBAT\)"\)',
            r'\(pad "2".*?\(net \d+ "GND"\)',
        ),
    )

    divider_sum = TOP_VALUE_MOHM + BOTTOM_VALUE_MOHM
    nominal = ceiling_v(TOP_VALUE_MOHM, BOTTOM_VALUE_MOHM)
    ratio_only_upper = ceiling_v(
        TOP_VALUE_MOHM, BOTTOM_VALUE_MOHM, DIVIDER_TOLERANCE
    )
    screening_upper = ceiling_v(
        TOP_VALUE_MOHM,
        BOTTOM_VALUE_MOHM,
        DIVIDER_TOLERANCE,
        THRESHOLD_ACCURACY,
    )
    operating_temperature_delta = max(
        abs(BQ25570_OPERATING_MIN_C - DIVIDER_REFERENCE_TEMP_C),
        abs(BQ25570_OPERATING_MAX_C - DIVIDER_REFERENCE_TEMP_C),
    )
    full_temperature_screening_upper = ceiling_v(
        TOP_VALUE_MOHM,
        BOTTOM_VALUE_MOHM,
        DIVIDER_TOLERANCE,
        THRESHOLD_ACCURACY,
        DIVIDER_TCR_PPM_PER_C,
        operating_temperature_delta,
    )
    history = historical_power(power_path)
    exact_payload = exact_payload_observation(ttn_path) if ttn_path else None
    gates = {
        "exact_bom_and_pcb_topology_bound": True,
        "divider_sum_within_ti_11_to_15Mohm_recommendation": (
            RECOMMENDED_DIVIDER_SUM_MIN_MOHM
            <= divider_sum
            <= RECOMMENDED_DIVIDER_SUM_MAX_MOHM
        ),
        "nominal_ceiling_below_5v5": nominal < ABSOLUTE_MAX_V,
        "flight3_observed_ceiling_below_5v5": history["maximum_v"] < ABSOLUTE_MAX_V,
        "bom_resistors_meet_ti_0v1pct_accuracy_condition": (
            DIVIDER_TOLERANCE <= DATASHEET_QUALIFYING_TOLERANCE
        ),
        "room_temperature_screening_upper_below_5v5": screening_upper < ABSOLUTE_MAX_V,
        "full_operating_temperature_screening_upper_below_5v5": (
            full_temperature_screening_upper < ABSOLUTE_MAX_V
        ),
    }
    if exact_payload is not None:
        gates["exact_payload_observed_ceiling_below_5v5"] = (
            exact_payload["maximum_v"] < ABSOLUTE_MAX_V
        )
    passed = all(gates.values())
    interpretation = (
        "Flight 3 stayed below 5.5 V in received telemetry, but its maximum "
        "is operation evidence rather than a production tolerance guarantee. "
        "The datasheet's overall +/-2% threshold guarantee is conditioned on "
        "0.1% resistors, but TI's BQ25570EVM guide explicitly computes min/max "
        "thresholds using +/-2% set-point accuracy plus +/-1% resistor "
        "tolerance. The conservative screen therefore follows a published TI "
        "design method. The current divider crosses both 5.5 V absolute "
        "maximums even before resistor TCR is included; opposite-signed "
        "100 ppm/C drift over the BQ25570 operating range makes it still higher."
    )
    if exact_payload is not None:
        interpretation += (
            f" The exact StratoLink-2 payload reported {exact_payload['maximum_v']:.3f} V "
            f"at fCnt {exact_payload['maximum_f_cnt']} before shading, with C5 "
            "absent. That remains below 5.5 V and is not calibrated threshold "
            "metrology, but proves the PPK2 source does not clamp solar charging."
        )
    interpretation += (
        " The selected supercapacitor is specified from 0.8 F to 1.2 F at "
        "23 C, so a nominal 1 F energy calculation is not a minimum-energy "
        "qualification. Lower-ratio divider examples are reported only to "
        "expose the overvoltage-versus-night-reserve tradeoff; they are not "
        "approved substitutions because no exact replacement part is bound "
        "and the fitted assembly remains unmeasured."
    )
    return {
        "passed": passed,
        "status": (
            "qualified_by_source_screen" if passed else
            "blocked_pending_safer_divider_or_exact_assembly_bound"
        ),
        "scope": (
            "source-bound DC charge-ceiling tolerance screen; not fitted-part "
            "metrology, transient capture, temperature characterization, or full-sun HIL"
        ),
        "sources": {
            "bq25570_datasheet": TI_DATASHEET,
            "bq25570_evm_user_guide": TI_EVM_GUIDE,
            "bq25570_evm_methodology": (
                "SLUUAA7A Rev. A, section 2, page 7 of the PDF: VBAT_OV "
                "min/max include +/-2% set-point accuracy and +/-1% resistor "
                "tolerance; section 2 also warns that residual flux is "
                "material beside 1-20 Mohm programming resistors"
            ),
            "supercap_datasheet": CAPXX_DATASHEET,
            "top_resistor_listing": R1_SOURCE,
            "bottom_resistor_listing": R2_SOURCE,
            "reference_top_resistor_datasheet": REFERENCE_TOP_SOURCE,
            "reference_top_resistor_listing": REFERENCE_TOP_LISTING,
            "safer_margin_top_resistor_datasheet": REFERENCE_TOP_SOURCE,
            "safer_margin_top_resistor_listing": SAFER_MARGIN_TOP_LISTING,
        },
        "exact_parts": {
            "charger": {"designator": CHARGER_DESIGNATOR, "part": CHARGER_PART, "lcsc": CHARGER_LCSC},
            "supercap": {
                "designator": SUPERCAP_DESIGNATOR,
                "part": SUPERCAP_PART,
                "rated_v": ABSOLUTE_MAX_V,
                "capacitance_f": {
                    "min": SUPERCAP_MIN_CAPACITANCE_F,
                    "typ": SUPERCAP_NOMINAL_CAPACITANCE_F,
                    "max": SUPERCAP_MAX_CAPACITANCE_F,
                },
                "esr_max_mohm_at_1khz": SUPERCAP_ESR_MAX_MOHM,
                "operating_temperature_c": [
                    SUPERCAP_OPERATING_MIN_C,
                    SUPERCAP_OPERATING_MAX_C,
                ],
                "cell_rated_v": SUPERCAP_CELL_RATED_V,
                "manufacturer_cell_capacitance_match_fraction": (
                    SUPERCAP_DUAL_CELL_MATCH_FRACTION
                ),
            },
            "divider_top": {"designator": TOP_DESIGNATOR, "part": TOP_PART, "lcsc": TOP_LCSC, "value_mohm": TOP_VALUE_MOHM, "tolerance_pct": 1.0, "tcr_ppm_per_c": DIVIDER_TCR_PPM_PER_C},
            "divider_bottom": {"designator": BOTTOM_DESIGNATOR, "part": BOTTOM_PART, "lcsc": BOTTOM_LCSC, "value_mohm": BOTTOM_VALUE_MOHM, "tolerance_pct": 1.0, "tcr_ppm_per_c": DIVIDER_TCR_PPM_PER_C},
        },
        "datasheet_limits": {
            "bq25570_and_supercap_absolute_max_v": ABSOLUTE_MAX_V,
            "bq25570_threshold_accuracy_pct": 2.0,
            "threshold_accuracy_resistor_condition_pct": 0.1,
            "ti_evm_design_screen_resistor_tolerance_pct": 1.0,
            "recommended_divider_sum_mohm": {
                "min": RECOMMENDED_DIVIDER_SUM_MIN_MOHM,
                "nominal": RECOMMENDED_DIVIDER_SUM_NOMINAL_MOHM,
                "max": RECOMMENDED_DIVIDER_SUM_MAX_MOHM,
            },
            "bq25570_operating_temperature_c": [
                BQ25570_OPERATING_MIN_C,
                BQ25570_OPERATING_MAX_C,
            ],
            "divider_reference_temperature_c": DIVIDER_REFERENCE_TEMP_C,
        },
        "calculated": {
            "divider_sum_mohm": round(divider_sum, 6),
            "nominal_ceiling_v": round(nominal, 6),
            "one_pct_ratio_only_upper_v": round(ratio_only_upper, 6),
            "conservative_screening_upper_v": round(screening_upper, 6),
            "room_temperature_screening_margin_to_5v5_v": round(
                ABSOLUTE_MAX_V - screening_upper, 6
            ),
            "operating_temperature_delta_c": operating_temperature_delta,
            "full_operating_temperature_screening_upper_v": round(
                full_temperature_screening_upper, 6
            ),
            "full_operating_temperature_screening_margin_to_5v5_v": round(
                ABSOLUTE_MAX_V - full_temperature_screening_upper, 6
            ),
        },
        "historical_flight3": history,
        "exact_payload_soak": exact_payload,
        "divider_tradeoff_screen": [
            screen_divider_option(value) for value in SCREENING_TOP_OPTIONS_MOHM
        ],
        "reference_rework_candidate": {
            "approval_state": "comparison_baseline_not_preferred_or_qualified",
            "designator": TOP_DESIGNATOR,
            "part": REFERENCE_TOP_PART,
            "value_mohm": REFERENCE_TOP_VALUE_MOHM,
            "package": "0402",
            "tolerance_pct": 1.0,
            "tcr_ppm_per_c": 100.0,
            "family_match": (
                "same lead-free Vishay D/CRCW e3 family as fitted R2 "
                f"{BOTTOM_PART}"
            ),
            "source_screen": screen_divider_option(REFERENCE_TOP_VALUE_MOHM),
            "why_not_qualified": (
                "availability and delivered identity are not frozen; voltage "
                "coefficient and assembly contamination are not bounded; the "
                "19 mV initial-cell source-screen margin is narrow; the "
                "reworked divider, active balancer, and fitted capacitor are unmeasured"
            ),
        },
        "safer_margin_prototype_candidate": {
            "approval_state": "source_screened_pending_manufacturer_review_and_hil",
            "designator": TOP_DESIGNATOR,
            "primary_part": SAFER_MARGIN_TOP_PART,
            "alternate_part": SAFER_MARGIN_TOP_ALTERNATE_PART,
            "value_mohm": SAFER_MARGIN_TOP_VALUE_MOHM,
            "package": "0402",
            "tolerance_pct": 1.0,
            "tcr_ppm_per_c": 100.0,
            "source_screen": screen_divider_option(SAFER_MARGIN_TOP_VALUE_MOHM),
            "headroom_gain_vs_7v50_reference_v": round(
                float(
                    screen_divider_option(SAFER_MARGIN_TOP_VALUE_MOHM)[
                        "worst_initial_cell_margin_to_2v75_v"
                    ]
                )
                - float(
                    screen_divider_option(REFERENCE_TOP_VALUE_MOHM)[
                        "worst_initial_cell_margin_to_2v75_v"
                    ]
                ),
                6,
            ),
            "why_not_qualified": (
                "the divider choice has not been accepted by CAP-XX; distributor "
                "availability and delivered identity are not frozen; voltage "
                "coefficient and assembly contamination are not bounded; the "
                "reworked threshold, active balancer, and fitted capacitor are unmeasured"
            ),
        },
        "interpretation": interpretation,
        "required_hil": (
            "With the exact flight supercap installed, use calibrated independent "
            "voltage instrumentation and transient capture to bound VBAT/VSTOR at "
            "maximum illumination and temperature corners. Measure the fitted "
            "capacitance/ESR and darkness reserve rather than assuming 1 F. Do not expose the cap "
            "to unbounded full sun; first lower/qualify the divider or use a "
            "current-limited controlled optical ramp with an abort below 5.5 V."
        ),
        "gates": gates,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--ttn",
        type=Path,
        help="optional frozen exact-payload TTN JSONL to bind direct VSTOR evidence",
    )
    parser.add_argument(
        "--allow-blocked",
        action="store_true",
        help="emit the expected blocked audit without a nonzero exit",
    )
    args = parser.parse_args()
    result = audit(ttn_path=args.ttn)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        if args.output.exists():
            raise SystemExit(f"refusing to overwrite charge-ceiling evidence: {args.output}")
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    if not result["passed"] and not args.allow_blocked:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
