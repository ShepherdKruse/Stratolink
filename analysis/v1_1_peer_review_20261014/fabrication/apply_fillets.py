#!/usr/bin/env python3
"""Apply only the audited local net-assigned fillet polygons and logo cleanup."""
from pathlib import Path
import json,hashlib,uuid,sys
import pcbnew,wx
app=wx.App(False)
p=Path(sys.argv[1]).resolve();assert '/ai-working/scratch/' in str(p)
b=pcbnew.LoadBoard(str(p));source=hashlib.sha256(p.read_bytes()).hexdigest()
plan=json.loads((p.parent/'fillet-plan.json').read_text());assert source==plan['source_sha256']
ids={};ledger=[]
def addpoly(name,points,layer,net=None):
 shape=pcbnew.PCB_SHAPE(b);shape.SetShape(pcbnew.SHAPE_T_POLY);shape.SetLayer(pcbnew.F_Cu if layer=='F.Cu' else pcbnew.B_Cu);shape.SetFilled(True);shape.SetWidth(0)
 poly=pcbnew.SHAPE_POLY_SET();poly.NewOutline()
 for x,y in points:poly.Append(round(x*1e6),round(y*1e6))
 shape.SetPolyShape(poly)
 if net and not net.startswith('ART:'):shape.SetNet(b.FindNet(net))
 stable=str(uuid.uuid5(uuid.NAMESPACE_URL,'stratolink-copper-fillets-20261014/'+name));ids[shape.m_Uuid.AsString()]=stable;b.Add(shape);ledger.append(dict(action='add_polygon',uuid=stable,name=name,net=net,layer=layer,points_mm=points))
for q in plan['patches']:addpoly(q['id']+'-'+str(q['sub']),q['points'],q['layer'],q['net'])
remove={'a816fba7-da64-4618-830a-b8a7043e1513','0c984686-78b1-4acf-8689-2d60d8705e9d','59a0671a-f542-4be7-b381-4ddca1c9e65a'}
seen=set()
for g in list(b.GetDrawings()):
 if g.m_Uuid.AsString() in remove:
  seen.add(g.m_Uuid.AsString());ledger.append(dict(action='remove_polygon',uuid=g.m_Uuid.AsString()));b.Remove(g)
assert seen==remove
logo=json.loads((p.parent/'logo-hole.json').read_text());addpoly('logo-hole-fill',logo['points'],'F.Cu')
pcbnew.SaveBoard(str(p),b);s=p.read_text()
for old,new in ids.items():s=s.replace(old,new)
p.write_text(s)
(p.parent/'fillet-changes.json').write_text(json.dumps(dict(source_sha256=source,pcb_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),changes=ledger),indent=2)+'\n')
print(len(ledger),'changes')
