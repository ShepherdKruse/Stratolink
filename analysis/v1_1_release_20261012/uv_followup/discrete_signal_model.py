#!/usr/bin/env python3
"""Illustrative UV photodiode/TIA arithmetic, not an ozone retrieval model.

Run with Python 3; the only output is discrete_signal_model.json in this folder.
Responsivities are single-wavelength typical values from the linked Genicom
datasheets in discrete-lcsc.md. Irradiances are chosen examples, not flight data.
"""
import json
import math
from pathlib import Path

area_m2 = 0.076e-6
adc_lsb_V = 3.3 / 4096
rows = []
for name, wavelength_nm, response_A_W, irradiance_W_m2, resistance_ohm in [
    ("GUVB-C21SD, 2018 sheet", 300, 0.11, 1.0, 10e6),
    ("GUVA-C22SD, 2020 sheet", 350, 0.14, 20.0, 1e6),
]:
    current_A = area_m2 * response_A_W * irradiance_W_m2
    rows.append({
        "detector": name,
        "monochromatic_wavelength_nm": wavelength_nm,
        "assumed_irradiance_W_per_m2": irradiance_W_m2,
        "active_area_m2": area_m2,
        "typical_responsivity_A_per_W": response_A_W,
        "feedback_R_ohm": resistance_ohm,
        "photocurrent_nA": current_A * 1e9,
        "signal_V_above_reference": current_A * resistance_ohm,
        "ideal_12bit_3V3_counts": current_A * resistance_ohm / adc_lsb_V,
        "irradiance_W_per_m2_per_ideal_ADC_LSB": adc_lsb_V / resistance_ohm / area_m2 / response_A_W,
        "feedback_resistor_input_noise_A_per_sqrt_Hz_at_25C": math.sqrt(4 * 1.380649e-23 * 298.15 / resistance_ohm),
    })

result = {
    "scope": "First-order signal/power arithmetic only; no solar spectrum, atmospheric retrieval, stability simulation, PCB qualification or ADC selection.",
    "adc": {"bits": 12, "reference_V": 3.3, "lsb_V": adc_lsb_V},
    "examples": rows,
    "LPV812_dual_typical_idle_W_at_3V3": 2 * 425e-9 * 3.3,
    "two_TSU111_typical_idle_W_at_3V3": 2 * 900e-9 * 3.3,
    "two_TSU111_max_idle_W_at_3V3_minus40_to_85C": 2 * 1480e-9 * 3.3,
    "TSU111_bias_bound_V_at_10Mohm_full_temperature": 50e-12 * 10e6,
    "reference_offset_buffer_ADC_power_included": False,
    "ten_Mohm_100pF_feedback_pole_Hz": 1 / (2 * math.pi * 10e6 * 100e-12),
    "one_Mohm_1nF_feedback_pole_Hz": 1 / (2 * math.pi * 1e6 * 1e-9),
    "capacitors_selected_or_stability_verified": False,
    "leakage_errors_at_10Mohm": [{"leakage_pA": p, "output_error_mV": p * 1e-12 * 10e6 * 1e3} for p in (1, 10, 100, 1000)],
}
Path(__file__).with_suffix(".json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
