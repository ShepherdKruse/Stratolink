#!/usr/bin/env python3
"""Read-only native inventory and polygons for every component PTH land."""
from pathlib import Path
import json,gzip,subprocess
import pcbnew as p,wx
H=Path(__file__).resolve().parent;ROOT=H.parents[2];BASE='d70a53d2093454084c9b1ae989d0276a88395334';S=Path.home()/'Repositories/ai-working/scratch/stratolink-edges-20261012/rings';S.mkdir(parents=True,exist_ok=True)
source=S/'baseline.kicad_pcb';source.write_bytes(subprocess.check_output(['git','show',BASE+':hardware/pcb/stratolink.kicad_pcb'],cwd=ROOT));app=wx.App(False);b=p.LoadBoard(str(source))
def chains(poly):
 def points(c):return [[c.CPoint(i).x/1e6,c.CPoint(i).y/1e6] for i in range(c.PointCount())]
 return [dict(shell=points(poly.Outline(i)),holes=[points(poly.Hole(i,j)) for j in range(poly.HoleCount(i))]) for i in range(poly.OutlineCount())]
def shape(item,l):
 poly=p.SHAPE_POLY_SET();item.TransformShapeToPolygon(poly,l,0,100,p.ERROR_OUTSIDE);return chains(poly)
outline=p.SHAPE_POLY_SET();assert b.GetBoardPolygonOutlines(outline,False,None,False,False)
items=[];pth=[];vias=[]
for f in b.GetFootprints():
 for pad in f.Pads():
  key=f.GetReference()+'.'+pad.GetNumber();layers={str(l):shape(pad,l) for l in [p.F_Cu,p.B_Cu,p.F_Mask,p.B_Mask] if pad.IsOnLayer(l)}
  item=dict(kind='pad',key=key,uuid=pad.m_Uuid.AsString(),net=pad.GetNetname(),polygons=layers);items.append(item)
  if pad.GetAttribute()==p.PAD_ATTRIB_PTH:
   pth.append(dict(key=key,uuid=pad.m_Uuid.AsString(),footprint=str(f.GetFPID().GetLibNickname())+':'+str(f.GetFPID().GetLibItemName()),at_mm=[pad.GetPosition().x/1e6,pad.GetPosition().y/1e6],net=pad.GetNetname(),size_mm=[pad.GetSize().x/1e6,pad.GetSize().y/1e6],drill_mm=[pad.GetDrillSize().x/1e6,pad.GetDrillSize().y/1e6],offset_mm=[pad.GetOffset().x/1e6,pad.GetOffset().y/1e6],shape=int(pad.GetShape()),layers=pad.GetLayerSet().FmtHex(),mask_margin_mm=pad.GetSolderMaskExpansion(p.F_Mask)/1e6,value=f.GetValue()))
for tr in b.GetTracks():
 layers={str(l):shape(tr,l) for l in [p.F_Cu,p.B_Cu] if tr.IsOnLayer(l)};items.append(dict(kind='via' if tr.Type()==p.PCB_VIA_T else 'track',uuid=tr.m_Uuid.AsString(),net=tr.GetNetname(),polygons=layers))
 if tr.Type()==p.PCB_VIA_T:vias.append(dict(uuid=tr.m_Uuid.AsString(),diameter_mm=tr.GetWidth(p.F_Cu)/1e6,drill_mm=tr.GetDrillValue()/1e6))
for z in b.Zones():
 if z.GetIsRuleArea():continue
 items.append(dict(kind='zone',uuid=z.m_Uuid.AsString(),net=z.GetNetname(),polygons={str(l):chains(z.GetFilledPolysList(l)) for l in [p.F_Cu,p.B_Cu] if z.IsOnLayer(l)}))
d=dict(baseline=BASE,outline=chains(outline),pth=pth,vias=vias,items=items)
(H/'native-audit.json.gz').write_bytes(gzip.compress(json.dumps(d,separators=(',',':')).encode(),mtime=0));print(len(pth),'PTH pads;',len(vias),'vias')
