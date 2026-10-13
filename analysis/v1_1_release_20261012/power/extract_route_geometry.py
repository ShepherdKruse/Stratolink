from pathlib import Path
import sys,json
import pcbnew,wx
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'analysis/v1_1_solar_attachments_20261012/materials'))
from extract_native import contours
DIR=Path.home()/'Repositories/ai-working/scratch/stratolink-release-20261012/power'
app=wx.App(False);b=pcbnew.LoadBoard(str(DIR/'balancer-candidate/stratolink.kicad_pcb'))
ib=pcbnew.LoadBoard(str(DIR.parent/'integrated-u7-r2/stratolink.kicad_pcb'))
items=[];holes=[];pads={}
newrefs={'U8','R24','R25','R26','C22'}
fps=[fp for fp in ib.GetFootprints() if fp.GetReference() not in newrefs]+[fp for fp in b.GetFootprints() if fp.GetReference() in newrefs]
def net(p):
 if isinstance(p,pcbnew.PAD) and p.GetParentFootprint().GetReference()=='C5' and p.GetNumber()=='3':return '/SC_MID'
 return p.GetNetname().replace('Net-(U1-VBAT)','/VBAT')
for fp in fps:
 for p in fp.Pads():
  label=fp.GetReference()+'.'+p.GetNumber();pos=[p.GetPosition().x/1e6,p.GetPosition().y/1e6]
  pads[label]=dict(at=pos,net=net(p),layers=[])
  for layer,name in [(pcbnew.F_Cu,'F.Cu'),(pcbnew.B_Cu,'B.Cu')]:
   if p.IsOnLayer(layer):
    poly=pcbnew.SHAPE_POLY_SET();p.TransformShapeToPolygon(poly,layer,0,1000,pcbnew.ERROR_OUTSIDE)
    items.append(dict(kind='pad',name=label,net=net(p),layer=name,polygons=contours(poly)));pads[label]['layers'].append(name)
  d=p.GetDrillSize()
  if d.x:holes.append(dict(at=pos,radius=max(d.x,d.y)/2e6,name=label))
for t in ib.GetTracks():
 if t.m_Uuid.AsString()=='acc183ca-d474-44e8-bd3c-69ef8aaafa23':continue
 if isinstance(t,pcbnew.PCB_VIA):holes.append(dict(at=[t.GetPosition().x/1e6,t.GetPosition().y/1e6],radius=t.GetDrillValue()/2e6,name=t.m_Uuid.AsString()))
 for layer,name in [(pcbnew.F_Cu,'F.Cu'),(pcbnew.B_Cu,'B.Cu')]:
  if t.IsOnLayer(layer):
   poly=pcbnew.SHAPE_POLY_SET();t.TransformShapeToPolygon(poly,layer,0,1000,pcbnew.ERROR_OUTSIDE)
   items.append(dict(kind='via' if isinstance(t,pcbnew.PCB_VIA) else 'track',name=t.m_Uuid.AsString(),net=net(t),layer=name,polygons=contours(poly)))
for g in ib.GetDrawings():
 if g.GetLayer() in [pcbnew.F_Cu,pcbnew.B_Cu]:
  poly=pcbnew.SHAPE_POLY_SET();g.TransformShapeToPolygon(poly,g.GetLayer(),0,1000,pcbnew.ERROR_OUTSIDE)
  items.append(dict(kind='drawing',name=g.m_Uuid.AsString(),net='',layer=b.GetLayerName(g.GetLayer()),polygons=contours(poly)))
edge=pcbnew.SHAPE_POLY_SET();b.GetBoardPolygonOutlines(edge,False)
(DIR/'route-geometry.json').write_text(json.dumps(dict(items=items,holes=holes,pads=pads,outline=contours(edge))))
print(len(items),len(holes),len(pads))
