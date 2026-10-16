#!/usr/bin/env python3
"""Read saved CAD; no refill/save. Export actual native copper unions and trace tangents."""
from pathlib import Path
import json,hashlib,sys,math
import pcbnew,wx
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'analysis/v1_1_solar_attachments_20261012/materials'))
from extract_native import contours

def xy(p):return [p.x/1e6,p.y/1e6]
def extract(path):
 raw=path.read_bytes();b=pcbnew.LoadBoard(str(path));b.GetDesignSettings().m_MaxError=2000;outline=pcbnew.SHAPE_POLY_SET();assert b.GetBoardPolygonOutlines(outline,False,None,False,False)
 result={'path':str(path),'sha256':hashlib.sha256(raw).hexdigest(),'outline':contours(outline),'copper':{},'tracks':[],'pad_rects':[]}
 for layer in [pcbnew.F_Cu,pcbnew.B_Cu]:
  p=pcbnew.SHAPE_POLY_SET();b.ConvertBrdLayerToPolygonalContours(layer,p);p.Simplify()
  result['copper'][b.GetLayerName(layer)]=contours(p)
 for t in b.GetTracks():
  if isinstance(t,pcbnew.PCB_VIA):continue
  d={'uuid':t.m_Uuid.AsString(),'net':t.GetNetname(),'kind':t.GetClass(),'start':xy(t.GetStart()),'end':xy(t.GetEnd()),'width':t.GetWidth()/1e6,'layer':b.GetLayerName(t.GetLayer()),'length':t.GetLength()/1e6}
  if isinstance(t,pcbnew.PCB_ARC):d['mid']=xy(t.GetMid())
  result['tracks'].append(d)
 for f in b.GetFootprints():
  for p in f.Pads():
   bb=p.GetBoundingBox();result['pad_rects'].append({'ref':f.GetReference(),'pin':p.GetNumber(),'net':p.GetNetname(),'bounds':[bb.GetLeft()/1e6,bb.GetTop()/1e6,bb.GetRight()/1e6,bb.GetBottom()/1e6]})
 assert path.read_bytes()==raw
 return result
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--pcb',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists(),a.output
 app=wx.App(False);r=extract(a.pcb);a.output.write_text(json.dumps(r,separators=(',',':'))+'\n');print(r['sha256'])
