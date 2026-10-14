#!/usr/bin/env python3
"""Apply frozen local RF-ECO copper repairs; never canonical files."""
from pathlib import Path
import sys,json,hashlib,uuid
import pcbnew,wx
p=Path(sys.argv[1]).resolve();assert '/ai-working/' in str(p)
plan=json.loads((p.parent/'rf-fillet-plan.json').read_text());source=hashlib.sha256(p.read_bytes()).hexdigest();assert source==plan['source_sha256']
app=wx.App(False);b=pcbnew.LoadBoard(str(p));ledger=[];ids={}
for q in plan['patches']:
 name=q['id']+'-'+str(q['sub']);shape=pcbnew.PCB_SHAPE(b);shape.SetShape(pcbnew.SHAPE_T_POLY);shape.SetLayer(pcbnew.F_Cu if q['layer']=='F.Cu' else pcbnew.B_Cu);shape.SetFilled(True);shape.SetWidth(0);shape.SetNet(b.FindNet(q['net']));poly=pcbnew.SHAPE_POLY_SET();poly.NewOutline()
 for x,y in q['points']:poly.Append(round(x*1e6),round(y*1e6))
 shape.SetPolyShape(poly);uid=str(uuid.uuid5(uuid.NAMESPACE_URL,'stratolink-rf-fillets-20261014/'+name));ids[shape.m_Uuid.AsString()]=uid;b.Add(shape);ledger.append(dict(action='polygon',uuid=uid,name=name,net=q['net'],layer=q['layer'],points=q['points'],planned_added_area_mm2=q['added_area_mm2']))
for z in b.Zones():z.UnFill()
pcbnew.SaveBoard(str(p),b);s=p.read_text()
for a,c in ids.items():s=s.replace(a,c)
old='(xy 53.5 47) (xy 55.8 47)';new='(xy 53.5 46.7) (xy 55.8 46.7)';assert s.count(old)==1;s=s.replace(old,new);ledger.append(dict(action='zone_first_two_vertices',uuid='ff68431e-1a69-589a-8846-12ef7f8f1c25',before=[[53.5,47],[55.8,47]],after=[[53.5,46.7],[55.8,46.7]],reason='Remove pointed GND wedge at AE2 clearance circle; add north-side reference bridge.'))
p.write_text(s);(p.parent/'rf-fillets-ledger.json').write_text(json.dumps(dict(source_sha256=source,changes=ledger),indent=2)+'\n');print('added',len(plan['patches']),'polygons')
