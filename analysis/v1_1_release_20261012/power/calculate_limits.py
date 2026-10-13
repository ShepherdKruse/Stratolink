#!/usr/bin/env python3
"""Recompute actual divider limits and transparent screening cases.

These are tolerance calculations, not measurements or component guarantees.
Uses ±2% set-point error and ±1% independent resistors, as TI's EVM guide does.
The optional temperature screen additionally assumes independent ±100 ppm/K
resistor drift across65 K from25°C to-40°C; it is not a fitted-board calibration.
"""
from pathlib import Path
import itertools,json,math
HERE=Path(__file__).resolve().parent

def corner(top,bottom,scale=1,tol=.01,tcr=0,delta=65):
 values=[]
 for a,b,e in itertools.product([-1,1],repeat=3):
  rt=top*(1+a*tol)*(1+a*tcr*1e-6*delta);rb=bottom*(1+b*tol)*(1+b*tcr*1e-6*delta)
  values.append(1.21*scale*(1+rt/rb)*(1+e*.02))
 return dict(nominal_V=1.21*scale*(1+top/bottom),minimum_V=min(values),maximum_V=max(values))

def main():
 source=json.loads((HERE/'actual-netmap.json').read_text());fp=source['footprints']
 r={ref:float(fp[ref]['value'].removesuffix('MΩ')) for ref in ['R1','R2','R3','R4','R5','R6','R7']}
 assert r==dict(R1=8.25,R2=4.22,R3=4.75,R4=3.65,R5=4.42,R6=8.25,R7=4.75)
 outputs={}
 for name,top,bottom,scale in [('existing_charge',r['R1'],r['R2'],1.5),('candidate_7M32_charge',7.32,r['R2'],1.5),('reference_7M50_charge',7.50,r['R2'],1.5),('reference_7M68_charge',7.68,r['R2'],1.5),('reference_7M87_charge',7.87,r['R2'],1.5),('buck_output',r['R6'],r['R7'],1),('good_falling',r['R3'],r['R5'],1),('good_rising',r['R3']+r['R4'],r['R5'],1)]:
  room=corner(top,bottom,scale);cold=corner(top,bottom,scale,tcr=100)
  outputs[name]=dict(room_1percent_2percent_screen=room,independent_TCR_100ppm_65K_screen=cold)
  if 'charge' in name:
   outputs[name]['cell_initial_52percent_upper_V']=cold['maximum_V']*.52
   outputs[name]['stack_max_margin_to_5p5_V']=5.5-cold['maximum_V']
 low=outputs['candidate_7M32_charge']['independent_TCR_100ppm_65K_screen']['minimum_V']
 high=outputs['candidate_7M32_charge']['independent_TCR_100ppm_65K_screen']['maximum_V']
 # Passive equal shunts: Vhigh≈Vstack/2 + R*ΔI/2. Guaranteed cell leakage
 # mismatch is NOT supplied at cold/end of life;6uA here is a sensitivity only.
 passive=[]
 for ohm in [10000,39000,100000,470000,1000000]:
  current_ua=high/(2*ohm)*1e6
  delta_allow_ua=(2*2.75-high)/ohm*1e6
  rc_only_h=.8*(2*ohm)*math.log(low/3.5)/3600
  passive.append(dict(per_cell_R_ohm=ohm,stack_shunt_current_at_upper_ua=current_ua,allowable_cell_leakage_difference_at_upper_ua=delta_allow_ua,RC_only_minC_runtime_from_lower_to3p5_h=rc_only_h))
 divhi=10e6*1.01*1.0065;divlo=10e6*.99*.9935
 active=dict(topology='CAP-XX Fig7; TLV8801 follower with feedback before22ohm isolation resistor; 10Mohm equal divider; 100nF local bypass',
  reference_max_fraction=divhi/(divhi+divlo),high_cell_screen_V=high*divhi/(divhi+divlo)+.0045,
  high_cell_margin_V=2.75-(high*divhi/(divhi+divlo)+.0045),
  divider_max_current_uA=high/(2*divlo)*1e6,
  initial_fourpercent_imbalance_22ohm_current_demand_mA=(high*.02)/22*1e3,
  rated_supply_max_V=5.5,supply_max_margin_V=5.5-high,
  low_supply_min_V=1.7,half_stack_within_specified_common_mode_above_V=1.8,
  typical_IC_Iq_uA=.450,Iq_table_max_25C_3p3V_uA=.700,
  typical_current_plus_divider_uA=.450+high/(2*divlo)*1e6,
  note='Offset max4.5mV is at25C; TCR is an independent65K screen. IQ and4.7mA drive are not guaranteed cold/full-voltage bounds. Required balancing current adds to idle current.')
 selected_charge=outputs['reference_7M50_charge']['independent_TCR_100ppm_65K_screen']
 selected_high=selected_charge['maximum_V'];selected_nom=selected_charge['nominal_V'];selected_lo=4.75e6*.99*.9935
 selected=dict(charge_R1_Mohm=7.50,divider_each_Mohm=4.75,screen=selected_charge,
  high_cell_screen_V=selected_high*divhi/(divhi+divlo)+.0045,
  high_cell_margin_V=2.75-(selected_high*divhi/(divhi+divlo)+.0045),
  initial_52percent_cell_V=selected_high*.52,
  divider_max_current_uA=selected_high/(2*selected_lo)*1e6,
  typical_IC_plus_divider_uA=.450+selected_high/(2*selected_lo)*1e6,
  illustrative_endpoint_V=2.51,nominal_capacitance_F=1,
  usable_nominal_energy_J=.5*(selected_nom**2-2.51**2),
  original_usable_nominal_energy_J=.5*(outputs['existing_charge']['room_1percent_2percent_screen']['nominal_V']**2-2.51**2),
  energy_note='Same illustrative endpoint and nominal capacitance; stored energy comparison is not night endurance. Offset limit is25C only; cold/ripple qualification remains required.')
 selected['usable_energy_reduction_fraction']=1-selected['usable_nominal_energy_J']/selected['original_usable_nominal_energy_J']
 result=dict(pcb_sha256=source['pcb_sha256'],actual_resistors_Mohm=r,thresholds=outputs,
 solar=dict(parallel_nameplate_W=2*4.8*.05,recommended_input_W=.4,peak_absolute_input_W=.510,recommended_Vin_V=5.1,absolute_Vin_V=5.5,configured_mppt_fraction=.8,minimum_boost_headroom_V=.4,proposed_low_corner_boost_Vin_ceiling_V=low-.4,implied_Voc_ceiling_by_headroom_only_V=(low-.4)/.8,scope='Panel4.8V label is ambiguous Voc/Vmp; actual coldVoc and available power not characterized. Open-circuit sampling must itself respect Vin ratings.'),
 buck=dict(shared_rail_voltage_rating_MAXM10S_V=3.6,output_current_min_93mA_typ_110mA_spec_conditions='VSTOR3.3V,VOUT1.8V; do not assume a guaranteed3.3V/cold current budget',radio_GNSS_concurrent_load_requires_measurement=True),
 passive_balance_sensitivity=passive,active_balance_screen=active,selected_pilot=selected,
 assertions=dict(existing_charge_room_corner_exceeds_5p5=outputs['existing_charge']['room_1percent_2percent_screen']['maximum_V']>5.5,candidate_7M32_stack_screen_below5p5=high<5.5,candidate_7M32_initial_match_screen_below2p75=high*.52<2.75,buck_screen_below_MAXM10S3p6=outputs['buck_output']['independent_TCR_100ppm_65K_screen']['maximum_V']<3.6),
 limitations=['No bounded cold/aged cell leakage mismatch: a total-stack ceiling alone does not establish long-term individual-cell safety.','Two source readings from a working board cannot establish worst-case tolerances for15 future assemblies.','The EVM method is a screening calculation; arbitrary1% divider parts do not inherit the datasheet±2% specification conditioned on0.1% resistors.','Footnote voltage headroom and input power limits coexist; they are not a claim of automatic protection.'])
 (HERE/'limits.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
