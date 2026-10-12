#!/usr/bin/env python3
"""Read canonical KiCad objects into polygon records. Never saves the PCB."""
import hashlib,json
from pathlib import Path
import pcbnew,wx
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
p=ROOT/'hardware/pcb/stratolink.kicad_pcb'
source=p.read_bytes(); app=wx.App(False);b=pcbnew.LoadBoard(str(p))
def contours(poly):
 def chain(c): return [[c.CPoint(i).x/1e6,c.CPoint(i).y/1e6] for i in range(c.PointCount())]
 return [{'shell':chain(poly.Outline(i)), 'holes':[chain(poly.Hole(i,j)) for j in range(poly.HoleCount(i))]} for i in range(poly.OutlineCount())]
def mm(v): return [v.x/1e6,v.y/1e6]
items=[]
for f in b.GetFootprints():
 for pad in f.Pads():
  for layer,name in [(pcbnew.F_Cu,'F.Cu'),(pcbnew.B_Cu,'B.Cu')]:
   if not pad.IsOnLayer(layer):continue
   poly=pcbnew.SHAPE_POLY_SET();pad.TransformShapeToPolygon(poly,layer,0,1000,pcbnew.ERROR_OUTSIDE)
   items.append(dict(type='pad',ref=f.GetReference(),pin=pad.GetNumber(),net=pad.GetNetname(),layer=name,uuid=pad.m_Uuid.AsString(),at_mm=mm(pad.GetPosition()),polygons=contours(poly)))
for t in b.GetTracks():
 for layer,name in [(pcbnew.F_Cu,'F.Cu'),(pcbnew.B_Cu,'B.Cu')]:
  if not t.IsOnLayer(layer):continue
  poly=pcbnew.SHAPE_POLY_SET();t.TransformShapeToPolygon(poly,layer,0,1000,pcbnew.ERROR_OUTSIDE)
  items.append(dict(type='via' if isinstance(t,pcbnew.PCB_VIA) else 'track',net=t.GetNetname(),layer=name,uuid=t.m_Uuid.AsString(),start_mm=mm(t.GetStart()),end_mm=mm(t.GetEnd()),width_mm=(t.GetWidth(layer) if isinstance(t,pcbnew.PCB_VIA) else t.GetWidth())/1e6,polygons=contours(poly)))
courtyards=[]
for f in b.GetFootprints():
 for layer,name in [(pcbnew.F_CrtYd,'F.CrtYd'),(pcbnew.B_CrtYd,'B.CrtYd')]:
  poly=f.GetCourtyard(layer)
  if poly.OutlineCount():courtyards.append(dict(ref=f.GetReference(),layer=name,polygons=contours(poly)))
result=dict(source_sha256=hashlib.sha256(source).hexdigest(),method='Native KiCad 10 TransformShapeToPolygon per object, 0.001 mm maximum outward approximation error; filled zones excluded because GND fill is regenerated after shape edits.',items=items,courtyards=courtyards)
assert p.read_bytes()==source
(HERE/'copper_native.json').write_text(json.dumps(result,separators=(',',':'))+'\n')
print(result['source_sha256'],len(items),'objects',len(courtyards),'courtyards')
