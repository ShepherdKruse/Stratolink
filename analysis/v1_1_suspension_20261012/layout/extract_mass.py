#!/usr/bin/env python3
"""Extract copper, mask opening, drill and outline polygons without CAD writes."""
from pathlib import Path
import subprocess,json,hashlib,sys
import pcbnew,wx
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'analysis/v1_1_solar_attachments_20261012/materials'))
from extract_native import contours
SCRATCH=Path.home()/'Repositories/ai-working/scratch/stratolink-suspension-mass'
SCRATCH.mkdir(parents=True,exist_ok=True)
BASE=SCRATCH/'baseline.kicad_pcb'
BASE.write_bytes(subprocess.check_output(['git','show','a9d6ed5:hardware/pcb/stratolink.kicad_pcb'],cwd=ROOT))
CANDIDATE=Path.home()/'Repositories/ai-working/scratch/stratolink-suspension-pth/candidate/stratolink.kicad_pcb'
app=wx.App(False);result={}
for label,path in [('baseline',BASE),('candidate',CANDIDATE)]:
 raw=path.read_bytes();b=pcbnew.LoadBoard(str(path))
 outline=pcbnew.SHAPE_POLY_SET();assert b.GetBoardPolygonOutlines(outline,False,None,False,False)
 layers={}
 for layer,name in [(pcbnew.F_Cu,'F.Cu'),(pcbnew.B_Cu,'B.Cu'),(pcbnew.F_Mask,'F.Mask'),(pcbnew.B_Mask,'B.Mask')]:
  poly=pcbnew.SHAPE_POLY_SET();b.ConvertBrdLayerToPolygonalContours(layer,poly);poly.Simplify();layers[name]=contours(poly)
 drills=[]
 for f in b.GetFootprints():
  for p in f.Pads():
   sz=p.GetDrillSize()
   if sz.x:
    drills.append(dict(ref=f.GetReference(),pad=p.GetNumber(),xy=[p.GetPosition().x/1e6,p.GetPosition().y/1e6],size=[sz.x/1e6,sz.y/1e6],rotation=p.GetOrientationDegrees(),plated=p.GetAttribute()!=pcbnew.PAD_ATTRIB_NPTH))
 for t in b.GetTracks():
  if isinstance(t,pcbnew.PCB_VIA):drills.append(dict(ref='via',pad='',xy=[t.GetPosition().x/1e6,t.GetPosition().y/1e6],size=[t.GetDrillValue()/1e6]*2,rotation=0,plated=True))
 circles=[dict(xy=[s.GetCenter().x/1e6,s.GetCenter().y/1e6],radius=s.GetRadius()/1e6) for s in b.GetDrawings() if s.GetLayer()==pcbnew.Edge_Cuts and s.GetShape()==pcbnew.SHAPE_T_CIRCLE]
 result[label]=dict(source_path=str(path),source_sha256=hashlib.sha256(raw).hexdigest(),thickness=b.GetDesignSettings().GetBoardThickness()/1e6,outline=contours(outline),layers=layers,drills=drills,edge_circles=circles)
 assert path.read_bytes()==raw
(HERE/'mass-native.json').write_text(json.dumps(result,separators=(',',':'))+'\n')
print({k:(v['source_sha256'],len(v['drills'])) for k,v in result.items()})
