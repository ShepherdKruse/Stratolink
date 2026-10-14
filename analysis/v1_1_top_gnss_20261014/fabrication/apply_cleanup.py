#!/usr/bin/env python3
"""Apply a frozen, hash-bound cleanup plan only to a scratch copy."""
from pathlib import Path
import json,hashlib,uuid,argparse
import pcbnew,wx
p=argparse.ArgumentParser();p.add_argument('--pcb',type=Path,required=True);p.add_argument('--plan',type=Path,required=True);p.add_argument('--ledger',type=Path,required=True);a=p.parse_args();assert a.pcb.resolve() != (Path(__file__).resolve().parents[3]/'hardware/pcb/stratolink.kicad_pcb').resolve(), 'Canonical PCB is forbidden; use an isolated candidate project.'
plan=json.loads(a.plan.read_text());source=hashlib.sha256(a.pcb.read_bytes()).hexdigest();assert source==plan['source_sha256']
app=wx.App(False);b=pcbnew.LoadBoard(str(a.pcb));ledger=[];ids={}
for q in plan['patches']:
 shape=pcbnew.PCB_SHAPE(b);shape.SetShape(pcbnew.SHAPE_T_POLY);shape.SetLayer(pcbnew.F_Cu if q['layer']=='F.Cu' else pcbnew.B_Cu);shape.SetFilled(True);shape.SetWidth(0);shape.SetNet(b.FindNet(q['net']));poly=pcbnew.SHAPE_POLY_SET();poly.NewOutline()
 for x,y in q['points']:poly.Append(round(x*1e6),round(y*1e6))
 shape.SetPolyShape(poly);uid=str(uuid.uuid5(uuid.NAMESPACE_URL,'stratolink-top-gnss-cleanup-20261014/'+q['id']));ids[shape.m_Uuid.AsString()]=uid;b.Add(shape);ledger.append(dict(action='add_same_net_fillet',uuid=uid,**q))
for q in plan['zone_holes']:
 zone=next(z for z in b.Zones() if z.m_Uuid.AsString()==q['zone_uuid']);outline=zone.Outline();assert outline.OutlineCount()==1
 hole=outline.NewHole(0)
 for x,y in q['points']:outline.Append(round(x*1e6),round(y*1e6),0,hole)
 ledger.append(dict(action='add_source_zone_hole',**q))
for q in plan.get('zone_boundaries',[]):
 zone=next(z for z in b.Zones() if z.m_Uuid.AsString()==q['zone_uuid']);outline=zone.Outline();assert outline.OutlineCount()==1 and outline.HoleCount(0)==0
 old=outline.COutline(0);assert [(old.CPoint(i).x/1e6,old.CPoint(i).y/1e6)for i in range(old.PointCount())]==[tuple(x)for x in q['before']]
 outline.RemoveAllContours();outline.NewOutline()
 for x,y in q['after']:outline.Append(round(x*1e6),round(y*1e6))
 ledger.append(dict(action='trim_solid_RF_zone_to_preserve_thermals',**q))
for z in b.Zones():z.UnFill()
pcbnew.SaveBoard(str(a.pcb),b);s=a.pcb.read_text()
for old,new in ids.items():s=s.replace(old,new)
a.pcb.write_text(s);a.ledger.write_text(json.dumps(dict(source_sha256=source,changes=ledger),indent=2)+'\n');print('applied',len(ledger),'changes')
