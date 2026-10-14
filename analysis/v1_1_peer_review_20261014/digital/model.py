#!/usr/bin/env python3
"""Conditional lumped-RC screening from actual routed centerline lengths.
Pin/fringing bounds are explicitly assumptions, not extracted IC guarantees.
No board or firmware edits; no electrostatic or IBIS simulation claimed.
"""
from pathlib import Path
import json,math
HERE=Path(__file__).resolve().parent
board=json.loads((HERE/'layout.json').read_text())['current']
def par(*r):return 1/sum(1/x for x in r)
def tr_ns(r,c):return math.log(.7/.3)*r*c*.001
pullups={'existing_4p7k_external_only':4700,'existing_with_GPS_8k_min':par(4700,8000),'existing_with_GPS_18k_typ':par(4700,18000),'existing_with_GPS_40k_max':par(4700,40000),'replace_with_two_10k_per_line':5000,'two10k_with_GPS18k':par(5000,18000),'single10k_per_line':10000}
lines={}
for bus,gps in [('SDA','Net-(U3-SDA)'),('SCL','Net-(U3-SCL)')]:
 n=board['nets'][bus];g=board['nets'][gps];L=n['total_track_mm']+g['total_track_mm']
 # TMP117 typical4pF; fiveotherpinloads3..10pF assumed each; pilotomitsone.
 full=[L*.04+4+5*3+5,L*.20+4+5*10+15]
 pilot=[L*.04+4+4*3+5,L*.20+4+4*10+15]
 lines[bus]={'main_routed_mm':n['total_track_mm'],'GNSS_branch_after_0ohm_mm':g['total_track_mm'],'all_copper_route_mm':L,'via_count':len(n['vias'])+len(g['vias']),'trace_widths_mm':sorted(set(t['width_mm'] for t in n['tracks']+g['tracks'])),
 'conditional_C_full_pF':full,'conditional_C_pilot_pF':pilot,'rise_ns_full':{name:[tr_ns(r,c) for c in full] for name,r in pullups.items()},'rise_ns_pilot':{name:[tr_ns(r,c) for c in pilot] for name,r in pullups.items()}}
# Show geometry-informed central-plane estimate, separate from conservative screening.
microstrip={}
for w in sorted(set(t['width_mm'] for b in ['SDA','SCL'] for t in board['nets'][b]['tracks'])):
 er=4.2;h=.31;t=.035
 eff=(er+1)/2+(er-1)/2*(1+12*h/w)**-.5
 z=87/math.sqrt(er+1.41)*math.log(5.98*h/(.8*w+t))
 cap=math.sqrt(eff)/(299792458*z)*1e9
 microstrip[str(w)]={'er_assumed':er,'height_mm':h,'estimated_Z0_ohm':z,'estimated_C_pF_per_mm':cap}
report={'pcb_sha256':board['sha256'],'model':'t30-70 = ln(0.7/0.3)*R*C = 0.8472978604 R C','conditional_assumptions':{'distributed_trace_C_pF_per_mm':[.04,.20],'TMP117_pin_C_pF_typical_not_max':4,'each_other_device_pin_C_pF_assumed':[3,10],'pad_via_module_fringe_extra_pF_assumed':[5,15],'external_cable_probe_C_pF':0,'full_connected_IC_count':6,'pilot_connected_IC_count':5,'C_bounds_are_assumed_engineering_screen_not_guaranteed_measured_limits':True},'plane_only_microstrip_reference':microstrip,'pullups_ohm':pullups,'bus':lines,'capacitance_limits_pF':{name:{'at_300ns':300e3/(math.log(.7/.3)*r),'at_1000ns_standard_mode_comparison_only':1000e3/(math.log(.7/.3)*r)} for name,r in pullups.items()},'static_sink_current_mA_at_3p3_and_Vol0p4_GPS8k_plus4p7k':(3.3-.4)/par(4700,8000)*1e3,'pulse_edge_warning':'Clock100kHz does not relax MAX-M10S/AS7331 published300ns edge requirement; probeactual30-70rise atfarloads.'}
(HERE/'rc-screen.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'bus':{k:{s:v[s] for s in ['all_copper_route_mm','via_count','conditional_C_full_pF','conditional_C_pilot_pF']} for k,v in lines.items()},'pullups':pullups,'plane_only':microstrip},indent=2))
