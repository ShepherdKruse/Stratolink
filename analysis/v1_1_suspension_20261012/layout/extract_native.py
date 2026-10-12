#!/usr/bin/env python3
"""Read-only canonical KiCad geometry extraction for the suspension screen."""
import hashlib, json
from pathlib import Path
import pcbnew, wx
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
SOURCE=ROOT/'hardware/pcb/stratolink.kicad_pcb'
raw=SOURCE.read_bytes()
app=wx.App(False)
b=pcbnew.LoadBoard(str(SOURCE))
def mm(v): return [v.x/1e6,v.y/1e6]
def contours(poly):
 def chain(c): return [mm(c.CPoint(i)) for i in range(c.PointCount())]
 return [{'shell':chain(poly.Outline(i)), 'holes':[chain(poly.Hole(i,j)) for j in range(poly.HoleCount(i))]} for i in range(poly.OutlineCount())]
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
outline=pcbnew.SHAPE_POLY_SET();valid=b.GetBoardPolygonOutlines(outline,False)
zones=[]
for z in b.Zones():
 for layer,name in [(pcbnew.F_Cu,'F.Cu'),(pcbnew.B_Cu,'B.Cu')]:
  if z.IsOnLayer(layer):zones.append(dict(net=z.GetNetname(),layer=name,rule_area=z.GetIsRuleArea(),polygons=contours(z.GetFilledPolysList(layer)),boundary=contours(z.Outline())))
edges=[]
for d in b.GetDrawings():
 if d.GetLayer()==pcbnew.Edge_Cuts:
  row=dict(shape=d.GetShapeStr(),uuid=d.m_Uuid.AsString(),start_mm=mm(d.GetStart()),end_mm=mm(d.GetEnd()),center_mm=mm(d.GetCenter()))
  if d.GetShape() in [pcbnew.SHAPE_T_CIRCLE,pcbnew.SHAPE_T_ARC]:row['radius_mm']=d.GetRadius()/1e6
  edges.append(row)
result=dict(source_sha256=hashlib.sha256(raw).hexdigest(),method='Native KiCad 10 polygons; maximum outward approximation error 0.001 mm.',items=items,courtyards=courtyards,zones=zones,outline_valid=valid,outline=contours(outline),edges=edges)
assert SOURCE.read_bytes()==raw
(HERE/'native.json').write_text(json.dumps(result,separators=(',',':'))+'\n')
print(result['source_sha256'],len(items),'copper objects',len(courtyards),'courtyards',len(zones),'zones')
