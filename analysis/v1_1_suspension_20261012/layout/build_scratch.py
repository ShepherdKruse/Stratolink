#!/usr/bin/env python3
"""Build a disposable suspension candidate; never edits canonical CAD."""
from pathlib import Path
import hashlib,json,shutil,subprocess
import pcbnew,wx
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
BASE='a9d6ed5'
OUT=Path.home()/'Repositories/ai-working/scratch/stratolink-suspension-pth/candidate'
OUT.mkdir(parents=True,exist_ok=True);(OUT/'lib').mkdir(exist_ok=True)
canonical=ROOT/'hardware/pcb/stratolink.kicad_pcb';raw=canonical.read_bytes()
for name in ['stratolink.kicad_pcb','stratolink.kicad_sch','stratolink.kicad_pro','fp-lib-table','sym-lib-table']:
 result=subprocess.run(['git','show',f'{BASE}:hardware/pcb/{name}'],cwd=ROOT,capture_output=True)
 if result.returncode==0:(OUT/name).write_bytes(result.stdout)
library_paths=subprocess.check_output(['git','ls-tree','-r','--name-only',BASE,'--','hardware/pcb/lib'],cwd=ROOT,text=True).splitlines()
for rel in library_paths:
 dest=OUT/Path(rel).relative_to('hardware/pcb');dest.parent.mkdir(parents=True,exist_ok=True)
 dest.write_bytes(subprocess.check_output(['git','show',f'{BASE}:{rel}'],cwd=ROOT))
name='Suspension_PTH_D2p0_OD3p2'
fp=f'''(footprint "{name}" (version 20260206) (generator "pcbnew") (layer "F.Cu")
 (descr "Manual string suspension: 2.0 mm finished plated hole, 3.2 mm GND pad, solid zone connection")
 (property "Reference" "REF**" (at 0 -2.3) (layer "F.Fab") (hide yes) (effects (font (size .7 .7) (thickness .1))))
 (property "Value" "Suspension 2.0 mm PTH" (at 0 2.3) (layer "F.Fab") (hide yes) (effects (font (size .7 .7) (thickness .1))))
 (attr through_hole board_only exclude_from_pos_files exclude_from_bom)
 (pad "1" thru_hole circle (at 0 0) (size 3.2 3.2) (drill 2.0) (layers "*.Cu" "*.Mask") (zone_connect 2))
 (fp_circle (center 0 0) (end 1.85 0) (stroke (width .05) (type solid)) (fill none) (layer "F.CrtYd"))
 (fp_circle (center 0 0) (end 1.85 0) (stroke (width .05) (type solid)) (fill none) (layer "B.CrtYd"))
)
'''
(OUT/'lib'/f'{name}.kicad_mod').write_text(fp)
board_text=(OUT/'stratolink.kicad_pcb').read_text()
added=[]
for ref,pos in [('H1',(55.665,31.745)),('H2',(74.327,31.745))]:
 placed=fp.replace(f'(footprint "{name}"',f'(footprint "lib:{name}"',1).replace('(layer "F.Cu")',f'(layer "F.Cu") (at {pos[0]} {pos[1]})',1).replace('"REF**"',f'"{ref}"',1).replace('(zone_connect 2)','(net "GND") (zone_connect 2)',1)
 added.append(placed)
(OUT/'stratolink.kicad_pcb').write_text(board_text.rstrip()[:-1]+'\n'+'\n'.join(added)+'\n)\n')
app=wx.App(False);b=pcbnew.LoadBoard(str(OUT/'stratolink.kicad_pcb'))
removed=[]
for d in list(b.GetDrawings()):
 if d.GetLayer()==pcbnew.Edge_Cuts and d.GetShape()==pcbnew.SHAPE_T_CIRCLE:
  removed.append(dict(uuid=d.m_Uuid.AsString(),center_mm=[d.GetCenter().x/1e6,d.GetCenter().y/1e6],radius_mm=d.GetRadius()/1e6));b.Remove(d)
assert len(removed)==2
b.BuildConnectivity()
pcbnew.SaveBoard(str(OUT/'stratolink.kicad_pcb'),b)
cli='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
run=subprocess.run([cli,'pcb','drc','--refill-zones','--save-board','--schematic-parity','--format','json','--output',str(HERE/'drc-project.json'),str(OUT/'stratolink.kicad_pcb')],check=True,text=True,capture_output=True)
(HERE/'project.log').write_text(run.stdout+run.stderr)
assert canonical.read_bytes()==raw,'Canonical changed during build'
report=dict(baseline=BASE,candidate=str(OUT),removed_edge_circles=removed,canonical_unchanged_sha256=hashlib.sha256(raw).hexdigest(),candidate_pcb_sha256=hashlib.sha256((OUT/'stratolink.kicad_pcb').read_bytes()).hexdigest())
(HERE/'build.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
