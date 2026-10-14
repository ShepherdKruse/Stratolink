#!/usr/bin/env python3
"""Read native saved geometry only. Never refill/save or alter the PCB."""
from pathlib import Path
import json,hashlib,sys,argparse
import pcbnew,wx
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'analysis/v1_1_solar_attachments_20261012/materials'))
from extract_native import contours,parse,one
args=argparse.ArgumentParser(description=__doc__)
args.add_argument('--pcb',type=Path,default=ROOT/'hardware/pcb/stratolink.kicad_pcb')
args.add_argument('--output',type=Path,default=HERE/'native-rf-geometry.json')
args.add_argument('--include-graphics',action='store_true',help='Include native PCB_SHAPE copper on board and footprints; report any copper text separately.')
args=args.parse_args()
p=args.pcb;raw=p.read_bytes();app=wx.App(False);b=pcbnew.LoadBoard(str(p));items=[]
for f in b.GetFootprints():
 for pad in f.Pads():
  for layer in [pcbnew.F_Cu,pcbnew.B_Cu]:
   if pad.IsOnLayer(layer):
    poly=pcbnew.SHAPE_POLY_SET();pad.TransformShapeToPolygon(poly,layer,0,2000,pcbnew.ERROR_OUTSIDE)
    items.append(dict(kind='pad',ref=f.GetReference(),pin=pad.GetNumber(),uuid=pad.m_Uuid.AsString(),net=pad.GetNetname(),layer=b.GetLayerName(layer),polygons=contours(poly),at=[pad.GetPosition().x/1e6,pad.GetPosition().y/1e6],drill=[v/1e6 for v in pad.GetDrillSize()]))
for t in b.GetTracks():
 for layer in [pcbnew.F_Cu,pcbnew.B_Cu]:
  if t.IsOnLayer(layer):
   poly=pcbnew.SHAPE_POLY_SET();t.TransformShapeToPolygon(poly,layer,0,2000,pcbnew.ERROR_OUTSIDE)
   item=dict(kind=type(t).__name__,uuid=t.m_Uuid.AsString(),net=t.GetNetname(),layer=b.GetLayerName(layer),polygons=contours(poly),start=[t.GetStart().x/1e6,t.GetStart().y/1e6],end=[t.GetEnd().x/1e6,t.GetEnd().y/1e6],width=(t.GetWidth(layer) if isinstance(t,pcbnew.PCB_VIA)else t.GetWidth())/1e6)
   if isinstance(t,pcbnew.PCB_ARC):item['mid']=[t.GetMid().x/1e6,t.GetMid().y/1e6]
   if isinstance(t,pcbnew.PCB_VIA):item['drill']=t.GetDrillValue()/1e6
   items.append(item)
for z in b.Zones():
 if z.GetIsRuleArea():continue
 for layer in [pcbnew.F_Cu,pcbnew.B_Cu]:
  if z.IsOnLayer(layer):items.append(dict(kind='zone',uuid=z.m_Uuid.AsString(),net=z.GetNetname(),layer=b.GetLayerName(layer),polygons=contours(z.GetFilledPolysList(layer))))
excluded_text=[]
if args.include_graphics:
 graphics=[(None,x)for x in b.GetDrawings()]+[(f.GetReference(),x)for f in b.GetFootprints()for x in f.GraphicalItems()]
 for ref,x in graphics:
  if x.GetLayer()not in[pcbnew.F_Cu,pcbnew.B_Cu]:continue
  if not isinstance(x,pcbnew.PCB_SHAPE):
   excluded_text.append(dict(uuid=x.m_Uuid.AsString(),ref=ref,layer=b.GetLayerName(x.GetLayer()),kind=type(x).__name__));continue
  layer=x.GetLayer();poly=pcbnew.SHAPE_POLY_SET();x.TransformShapeToPolygon(poly,layer,0,2000,pcbnew.ERROR_OUTSIDE)
  items.append(dict(kind='graphic',ref=ref,uuid=x.m_Uuid.AsString(),net=x.GetNetname(),layer=b.GetLayerName(layer),polygons=contours(poly)))
footprints={}
for f in b.GetFootprints():
 box=f.GetBoundingBox(False,False);body=[]
 for s in f.GraphicalItems():
  if s.GetLayer()in[pcbnew.F_Fab,pcbnew.B_Fab] and isinstance(s,pcbnew.PCB_SHAPE):
   bb=s.GetBoundingBox();body.append([bb.GetLeft()/1e6,bb.GetTop()/1e6,bb.GetRight()/1e6,bb.GetBottom()/1e6])
 footprints[f.GetReference()]=dict(at=[f.GetPosition().x/1e6,f.GetPosition().y/1e6],value=f.GetValue(),layer=f.GetLayerName(),bounds=[box.GetLeft()/1e6,box.GetTop()/1e6,box.GetRight()/1e6,box.GetBottom()/1e6],body_graphics=body)
tree=parse(raw.decode());result=dict(pcb_sha256=hashlib.sha256(raw).hexdigest(),project_sha256=hashlib.sha256((p.parent/'stratolink.kicad_pro').read_bytes()).hexdigest(),source=str(p),graphics_included=args.include_graphics,excluded_copper_text=excluded_text,kicad=pcbnew.GetBuildVersion(),stackup=one(one(tree,'setup'),'stackup'),items=items,footprints=footprints,notes=['Uses exact saved native fill. No refill/save; copper identical to previously verified final native fill.','Curved copper outlines approximated with <=2 um requested native polygon error, ERROR_OUTSIDE.'])
assert p.read_bytes()==raw
args.output.write_text(json.dumps(result,separators=(',',':'))+'\n');print(len(items),result['pcb_sha256']);print('stackup',result['stackup'])
