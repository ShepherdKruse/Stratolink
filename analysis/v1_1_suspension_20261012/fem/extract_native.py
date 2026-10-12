#!/usr/bin/env python3
"""Run with KiCad Python; extract frozen original upper-board geometry."""
from pathlib import Path
import hashlib, json, subprocess
import pcbnew, wx
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
raw=subprocess.check_output(['git','show','a9d6ed5:hardware/pcb/stratolink.kicad_pcb'],cwd=ROOT)
work=Path.home()/'Repositories/ai-working/scratch/stratolink-suspension-fem'
work.mkdir(parents=True,exist_ok=True)
path=work/'baseline.kicad_pcb';path.write_bytes(raw)
app=wx.App(False);board=pcbnew.LoadBoard(str(path))
poly=pcbnew.SHAPE_POLY_SET();board.GetBoardPolygonOutlines(poly,False,None,False,False)
assert poly.OutlineCount()==1
chain=poly.COutline(0)
shell=[[chain.CPoint(i).x/1e6,chain.CPoint(i).y/1e6] for i in range(chain.PointCount())]
drills=[]
for footprint in board.GetFootprints():
 for pad in footprint.Pads():
  pos=pad.GetPosition();size=pad.GetDrillSize()
  if size.x and pos.y/1e6<46:
   drills.append(dict(at=[pos.x/1e6,pos.y/1e6],diameter=[size.x/1e6,size.y/1e6],ref=footprint.GetReference()))
for track in board.GetTracks():
 if isinstance(track,pcbnew.PCB_VIA):
  pos=track.GetPosition();diameter=track.GetDrillValue()/1e6
  if pos.y/1e6<46:drills.append(dict(at=[pos.x/1e6,pos.y/1e6],diameter=[diameter,diameter],ref='via'))
result=dict(board_sha256=hashlib.sha256(raw).hexdigest(),shell=shell,drills=drills)
(HERE/'input.json').write_text(json.dumps(result,indent=2)+'\n')
print(f'Extracted {len(shell)} outline vertices and {len(drills)} upper drills')
