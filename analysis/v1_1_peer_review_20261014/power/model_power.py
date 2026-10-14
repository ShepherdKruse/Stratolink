#!/usr/bin/env python3
"""Illustrative capacitance/charge-balance screens; not a regulator simulation."""
from pathlib import Path
import json,math,xml.etree.ElementTree as ET
HERE=Path(__file__).resolve().parent
curves=json.loads((HERE/'capacitor-curves.json').read_text())
board=json.loads((HERE/'native-power.json').read_text())
def dc(part,v):return curves[part]['curves']['DCBias']['typical_uF'][str(v)]
parts={'C6':('CL21A226MAYNNN',22,.20),'C8':('CL10A106KP8NNN',10,.10),'C21':('CL10A106KP8NNN',10,.10),'C16':('CL10A475KP8NNN',4.7,.10)}
scenarios={}
for name,refs in [('retained',['C6','C8','C21','C16']),('omit_C21',['C6','C8','C16']),('omit_C8_and_C21',['C6','C16']),('C6_only',['C6'])]:
    nominal=sum(parts[r][1] for r in refs)
    typical=sum(dc(parts[r][0],3.3) for r in refs)
    tolerance_screen=sum(dc(parts[r][0],3.3)*(1-parts[r][2]) for r in refs)
    scenarios[name]={'refs':refs,'nominal_uF':nominal,'typical_25C_3p3V_sum_uF':typical,'illustrative_low_initial_tolerance_screen_uF':tolerance_screen,'droop_V_100mA_10us':.1*10e-6/(typical*1e-6),'droop_V_100mA_100us':.1*100e-6/(typical*1e-6)}
def pt(ref,pin):return board['footprints'][ref]['pads'][pin]['at_mm']
separations={}
for a,b in [(('C8','2'),('U2','24')),(('C7','2'),('U2','24')),(('C21','2'),('C6','2')),(('C10','1'),('U3','8')),(('C6','2'),('U1','14')),(('C3','1'),('U1','19')),(('C2','1'),('U1','2')),(('C4','1'),('U1','19'))]:
    separations['.'.join(a)+' to '+'.'.join(b)]=math.dist(pt(*a),pt(*b))
result={'warning':'A charge-balance illustration, not closed-loop simulation or guaranteed capacitance. Sums ignore ESR/ESL/traces/feedback and do not prove locally available capacitance. Small bypass capacitors are omitted from sums. Temperature, aging and AC-amplitude effects are not multiplied into a false guaranteed bound.','source_pcb_sha256':board['sha256'],'scenarios':scenarios,'straight_line_pad_center_distances_mm_not_trace_lengths':separations,'package_body_only':{'0603_each_mm':[1.6,.8,.8],'0402_candidate_each_mm':[1,.5,.5],'pair_nominal_body_area_saved_mm2':2*(1.6*.8-1*.5),'pair_nominal_body_volume_saved_mm3':2*(1.6*.8*.8-1*.5*.5),'mass_not_specified_or_measured':True}}
(HERE/'power-screen.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
