#!/usr/bin/env python3
"""Read-only native mechanical envelope input export."""
from pathlib import Path
import pcbnew,wx,json,sys,hashlib
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'analysis/v1_1_solar_attachments_20261012/materials'));from extract_native import contours
p=Path(sys.argv[1]);out=Path(sys.argv[2]);raw=p.read_bytes();app=wx.App(False);b=pcbnew.LoadBoard(str(p));d={'source':str(p),'sha256':hashlib.sha256(raw).hexdigest(),'footprints':{},'pads':[],'models':{}}
def xy(q):return[q.x/1e6,q.y/1e6]
for f in b.GetFootprints():
 ref=f.GetReference();body=[]
 for g in f.GraphicalItems():
  if isinstance(g,pcbnew.PCB_SHAPE) and g.GetLayer() in [pcbnew.F_Fab,pcbnew.B_Fab]:
   bb=g.GetBoundingBox();body.append([bb.GetLeft()/1e6,bb.GetTop()/1e6,bb.GetRight()/1e6,bb.GetBottom()/1e6])
 d['footprints'][ref]={'at':xy(f.GetPosition()),'angle':f.GetOrientationDegrees(),'layer':f.GetLayerName(),'fab_boxes':body}
 d['models'][ref]=[dict(file=m.m_Filename,offset=[m.m_Offset.x,m.m_Offset.y,m.m_Offset.z],rotation=[m.m_Rotation.x,m.m_Rotation.y,m.m_Rotation.z],scale=[m.m_Scale.x,m.m_Scale.y,m.m_Scale.z]) for m in f.Models()]
 for q in f.Pads():
  for layer in [pcbnew.F_Cu,pcbnew.B_Cu]:
   if q.IsOnLayer(layer):
    poly=pcbnew.SHAPE_POLY_SET();q.TransformShapeToPolygon(poly,layer,0,1000,pcbnew.ERROR_OUTSIDE);d['pads'].append(dict(ref=ref,pin=q.GetNumber(),net=q.GetNetname(),at=xy(q.GetPosition()),drill=xy(q.GetDrillSize()),size=xy(q.GetSize()),layer=b.GetLayerName(layer),polygons=contours(poly)))
poly=pcbnew.SHAPE_POLY_SET();assert b.GetBoardPolygonOutlines(poly,False,None,False,False);d['outline']=contours(poly);out.write_text(json.dumps(d,indent=2)+'\n');assert p.read_bytes()==raw
