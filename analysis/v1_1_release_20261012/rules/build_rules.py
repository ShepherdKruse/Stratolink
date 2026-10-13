#!/usr/bin/env python3
"""Stage explicit supplier rules in scratch; never mutate canonical CAD."""
from pathlib import Path
import json,subprocess
HERE=Path(__file__).resolve().parent
OUT=Path.home()/'Repositories/ai-working/scratch/stratolink-release-20261012/rules'
pro=OUT/'stratolink.kicad_pro'
p=json.loads(pro.read_text())
s=p['board']['design_settings']
s['rules'].update(min_clearance=.1,min_copper_edge_clearance=.2,min_track_width=.1)
for key in ['clearance','copper_edge_clearance','annular_width']:
 s['rule_severities'][key]='error'
p['net_settings']['classes'][0]['clearance']=.15
pro.write_text(json.dumps(p,indent=2)+'\n')
# Existing architecture is below6V, not an isolation barrier. Preserve0.15mm
# default routing margin above the manufacturer's0.10mm manufacturing floor.
# The exceptions below are scoped to specific fine-pitch components/corridors.
rules='''(version 1)
# JLC two-layer 1oz ENIG: >=0.10mm copper spacing, >=0.20mm routed edge.
# Default net-class routing target is0.15mm; existing0.20mm diagnostic retained.
# Exact source and release dispositions: analysis/v1_1_release_20261012/rules.

(rule "JLC component lead hole annulus"
 (condition "A.Type == 'Pad' && A.Pad_Type == 'Through-hole' && !A.memberOfFootprint('U1')")
 (constraint annular_width (min 0.18mm)))

(rule "JLC component lead hole to foreign copper"
 (condition "(A.Type == 'Pad' && A.Pad_Type == 'Through-hole' && !A.memberOfFootprint('U1')) || (B.Type == 'Pad' && B.Pad_Type == 'Through-hole' && !B.memberOfFootprint('U1'))")
 (constraint hole_clearance (min 0.28mm)))

(rule "J3 one millimetre pitch pad spacing"
 (condition "A.Type == 'Pad' && B.Type == 'Pad' && A.memberOfFootprint('J3') && B.memberOfFootprint('J3')")
 (constraint clearance (min 0.12mm)))

(rule "J4 one millimetre pitch pad spacing"
 (condition "A.Type == 'Pad' && B.Type == 'Pad' && A.memberOfFootprint('J4') && B.memberOfFootprint('J4')")
 (constraint clearance (min 0.12mm)))

(rule "U7 fine pitch lands"
 (condition "A.Type == 'Pad' && B.Type == 'Pad' && A.memberOfFootprint('U7') && B.memberOfFootprint('U7')")
 (constraint clearance (min 0.10mm)))

(rule "R23 pads beside VSTOR"
 (condition "(A.memberOfFootprint('R23') && B.Type == 'Track' && B.NetName == 'VSTOR') || (B.memberOfFootprint('R23') && A.Type == 'Track' && A.NetName == 'VSTOR')")
 (constraint clearance (min 0.13mm)))
'''
(OUT/'stratolink.kicad_dru').write_text(rules)
(HERE/'candidate.kicad_dru').write_text(rules)
result=subprocess.run(['/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli','pcb','drc','--refill-zones','--all-track-errors','--schematic-parity','--format','json','--output',str(HERE/'supplier-rules-drc.json'),str(OUT/'stratolink.kicad_pcb')],capture_output=True,text=True)
(OUT/'rules.log').write_text(result.stdout+result.stderr)
print(result.stdout);print('Exit:',result.returncode)
if result.returncode: print(result.stderr[-3000:])
else:
 d=json.loads((HERE/'supplier-rules-drc.json').read_text())
 for v in d['violations']:
  if v['type'] not in ['lib_footprint_mismatch','silk_over_copper']: print(v)
