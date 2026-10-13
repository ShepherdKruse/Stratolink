#!/usr/bin/env python3
import gzip
from pathlib import Path
import pcbnew,wx,json
H=Path(__file__).resolve().parent;ROOT=H.parents[2];S=Path.home()/'Repositories/ai-working/scratch/stratolink-zones-20261012/thermal';app=wx.App(False)
def chains(poly):
 def pts(c):return [[c.CPoint(i).x/1e6,c.CPoint(i).y/1e6] for i in range(c.PointCount())]
 return [dict(shell=pts(poly.Outline(i)),holes=[pts(poly.Hole(i,j)) for j in range(poly.HoleCount(i))]) for i in range(poly.OutlineCount())]
def shape(item):
 p=pcbnew.SHAPE_POLY_SET();item.TransformShapeToPolygon(p,pcbnew.F_Cu,0,100,pcbnew.ERROR_OUTSIDE);return chains(p)
result={}
for label,path in [('baseline',ROOT/'hardware/pcb/stratolink.kicad_pcb'),('mixed',S/'mixed_g250_w250_j20direct/stratolink.kicad_pcb')]:
 if not path.exists():path=S/'mixed_g200_w250_j20direct/stratolink.kicad_pcb'
 b=pcbnew.LoadBoard(str(path));items=[]
 for f in b.GetFootprints():
  for p in f.Pads():
   if p.IsOnLayer(pcbnew.F_Cu):items.append(dict(type='pad',ref=f.GetReference(),pin=p.GetNumber(),net=p.GetNetname(),at=[p.GetPosition().x/1e6,p.GetPosition().y/1e6],polygons=shape(p)))
 for t in b.GetTracks():
  if t.IsOnLayer(pcbnew.F_Cu):items.append(dict(type='track',net=t.GetNetname(),polygons=shape(t)))
 zones=[]
 for z in b.Zones():
  if z.IsOnLayer(pcbnew.F_Cu) and z.GetNetname()=='GND':zones.extend(chains(z.GetFilledPolysList(pcbnew.F_Cu)))
 result[label]=dict(path=str(path),zones=zones,items=items)
(H/'regions.json.gz').write_bytes(gzip.compress((json.dumps(result,separators=(',',':'))+'\n').encode(),mtime=0))
