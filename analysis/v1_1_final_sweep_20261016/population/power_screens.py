#!/usr/bin/env python3
"""Recompute bounded power screens for the audited live values, without CAD edits."""
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
spec = importlib.util.spec_from_file_location('existing_limits', ROOT / 'analysis/v1_1_release_20261012/power/calculate_limits.py')
limits = importlib.util.module_from_spec(spec)
spec.loader.exec_module(limits)
audit = json.loads((HERE / 'audit.json').read_text())
values = audit['power_values']
r = {name: float(values[name].removesuffix('MΩ')) for name in ['R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'R7', 'R24', 'R25']}
thresholds = {}
for name, top, bottom, scale in [('charge', r['R1'], r['R2'], 1.5), ('buck', r['R6'], r['R7'], 1),
                                 ('VBAT_OK_falling', r['R3'], r['R5'], 1),
                                 ('VBAT_OK_rising', r['R3'] + r['R4'], r['R5'], 1)]:
    thresholds[name] = {'room_screen': limits.corner(top, bottom, scale),
                        'independent_100ppm_TCR_65K_screen': limits.corner(top, bottom, scale, tcr=100)}
charge = thresholds['charge']['independent_100ppm_TCR_65K_screen']
rh = r['R24'] * 1.01 * 1.0065
rl = r['R25'] * .99 * .9935
cell = charge['maximum_V'] * rh / (rh + rl) + .0045
result = {
    'source_sha256': audit['source_sha256'], 'actual_resistors_Mohm': r, 'thresholds': thresholds,
    'balancer': {
        'feedback_before_R26_confirmed_in_audit': True,
        'screened_high_cell_V': cell, 'margin_to_2p75_V': 2.75 - cell,
        'initial_52percent_split_high_cell_V': .52 * charge['maximum_V'],
        'typical_IC_plus_screened_divider_uA': .450 + charge['maximum_V'] / (2 * rl),
        'offset_assumption_V': .0045, 'offset_limit_temperature_C': 25,
        'common_mode_valid_half_stack_above_V': 1.8,
        'supply_rated_V': [1.7, 5.5],
        'nominal_energy_J_at_1F_to_2p51V': .5 * (charge['nominal_V'] ** 2 - 2.51 ** 2),
    },
    'L2_conditional_current_screen': {
        'TI_cycle_limit_max_mA': 205, 'TI_test_VSTOR_V': [2.4, 5.5], 'TI_test_VOUT_upper_exclusive_V': 3.3,
        'TI_25percent_margin_threshold_mA': 205 * 1.25,
        'manufacturer_Isat_typ_mA_at_25C': 280, 'manufacturer_Irms_typ_mA_at_25C': 280,
        'typical_rating_margin_mA': 280 - 205 * 1.25,
        'guaranteed_current_margin_established': False, 'DCR_max_ohm_at_25C': 2.405,
        'illustrative_100mA_DC_copper_loss_mW': .1 ** 2 * 2.405 * 1000,
        'note': 'Typical inductor currents are not guaranteed cold limits; actual 3.3116 V set point exceeds the stated <3.3 V current-limit test interval. DC copper loss is not switching loss.',
    },
    'solar_screen': {
        'two_parallel_nameplates_W': 2 * 4.8 * .05, 'TI_recommended_input_W': .4, 'TI_absolute_peak_input_W': .510,
        'TI_recommended_VIN_V': 5.1, 'TI_absolute_VIN_V': 5.5,
        'MPPT_fraction': .8, 'charge_low_corner_minus_400mV_headroom_V': charge['minimum_V'] - .4,
        'safe_cold_Voc_or_available_power_demonstrated': False,
        'note': 'The panel label does not define guaranteed Voc/Isc, and MPPT open-circuit sampling is not an input clamp.',
    },
    'limitations': [
        '1% resistors and 100ppm/K independent drift are screening assumptions, not the TI guarantee conditioned on 0.1% resistors.',
        'No transient, ripple, low-temperature electrochemistry or unpowered op-amp simulation is represented.',
        'The balancer offset limit is a 25C figure, not a guaranteed cold maximum.',
        'Stored energy is not runtime or night endurance.',
    ],
}
(HERE / 'power-screens.json').write_text(json.dumps(result, indent=2) + '\n')
print('Power screens recomputed for ' + audit['source_sha256']['live/stratolink.kicad_pcb'])
