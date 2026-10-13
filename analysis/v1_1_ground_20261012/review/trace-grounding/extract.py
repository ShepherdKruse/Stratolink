#!/usr/bin/env python3
"""Trace-fed U7 grounding experiment on a disposable zone-free board copy."""
from pathlib import Path
import sys,hashlib,subprocess,json
import pcbnew,wx
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'analysis/v1_1_solar_attachments_20261012/materials'));from extract_native import contours
BASE='c3d70a4';raw=subprocess.check_output(['git','show',BASE+':hardware/pcb/stratolink.kicad_pcb'],cwd=ROOT);text=raw.decode()
scratch=Path.home()/'Repositories/ai-working/scratch/stratolink-zones-20261012/trace-audit';scratch.mkdir(parents=True,exist_ok=True)
stack=[];quoted=False;escape=False;spans=[]
for i,c in enumerate(text):
 if quoted:
  if escape:escape=False
  elif c=='\\':escape=True
  elif c=='"':quoted=False
 elif c=='"':quoted=True
 elif c=='(':stack.append(i)
 elif c==')':
  start=stack.pop()
  if len(stack)==1 and text[start:start+5]=='(zone':spans.append((start,i+1))
for start,end in reversed(spans):text=text[:start]+text[end:]
path=scratch/'without-zones.kicad_pcb';path.write_text(text)
app=wx.App(False);board=pcbnew.LoadBoard(str(path));con=board.GetConnectivity();assert len(list(board.Zones()))==0
u7=next(f for f in board.GetFootprints() if f.GetReference()=='U7')
def item_data(item):
 if item.GetClass()=='PCB_VIA':item=pcbnew.Cast_to_PCB_VIA(item)
 row=dict(uuid=item.m_Uuid.AsString(),type=item.GetClass(),net=item.GetNetname(),layers={})
 if isinstance(item,pcbnew.PAD):row.update(ref=item.GetParentFootprint().GetReference(),pin=item.GetNumber(),xy=[item.GetPosition().x/1e6,item.GetPosition().y/1e6])
 if isinstance(item,pcbnew.PCB_TRACK):row.update(start=[item.GetStart().x/1e6,item.GetStart().y/1e6],end=[item.GetEnd().x/1e6,item.GetEnd().y/1e6],width_mm=(item.GetWidth(pcbnew.F_Cu) if isinstance(item,pcbnew.PCB_VIA) else item.GetWidth())/1e6,length_mm=item.GetLength()/1e6)
 if isinstance(item,pcbnew.PCB_VIA):row.update(drill_mm=item.GetDrillValue()/1e6)
 for layer,name in [(pcbnew.F_Cu,'F.Cu'),(pcbnew.B_Cu,'B.Cu')]:
  if item.IsOnLayer(layer):
   poly=pcbnew.SHAPE_POLY_SET();item.TransformShapeToPolygon(poly,layer,0,1000,pcbnew.ERROR_OUTSIDE);row['layers'][name]=contours(poly)
 return row
groups={};items={}
for pad in u7.Pads():
 if pad.GetNumber() not in ['3','5','6','7','8']:continue
 connected=list(con.GetConnectedItems(pad));uuids=set()
 for item in [pad]+connected:
  uuid=item.m_Uuid.AsString();items[uuid]=item_data(item);uuids.add(uuid)
 groups[pad.GetNumber()]=dict(pad_uuid=pad.m_Uuid.AsString(),item_uuids=sorted(uuids),reachable_pads=sorted(set((i.GetParentFootprint().GetReference(),i.GetNumber()) for i in [pad]+connected if isinstance(i,pcbnew.PAD))),reachable_vias=[i.m_Uuid.AsString() for i in connected if i.GetClass()=='PCB_VIA'])
result=dict(baseline=BASE,source_sha256=hashlib.sha256(raw).hexdigest(),zone_free_source=str(path),zone_free_sha256=hashlib.sha256(text.encode()).hexdigest(),removed_zone_count=len(spans),groups=groups,items=items)
(HERE/'native.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='items'},indent=2))
