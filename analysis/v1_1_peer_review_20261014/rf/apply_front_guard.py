from pathlib import Path
import json,pcbnew,wx,sys,uuid,hashlib,shutil
H=Path(__file__).resolve().parent;plan=json.loads((H/'front-guard-plan.json').read_text());p=Path(sys.argv[1]);assert '/ai-working/scratch/'in str(p)
raw=p.read_text()
assert str(uuid.uuid5(uuid.NAMESPACE_URL,'stratolink-rf-front-guard-20261014'))not in raw,'Guard already present; do not apply twice.'
while'(filled_polygon'in raw:
 st=raw.index('(filled_polygon');depth=0
 for e in range(st,len(raw)):
  if raw[e]=='(':depth+=1
  elif raw[e]==')':
   depth-=1
   if depth==0:break
 raw=raw[:st]+raw[e+1:]
p.write_text(raw);app=wx.App(False);b=pcbnew.LoadBoard(str(p));changes=[];ids={}
def pt(v):return pcbnew.VECTOR2I(round(v[0]*1e6),round(v[1]*1e6))
for g in b.Groups():
 if g.GetName()in plan['moves']:g.Move(pt(plan['moves'][g.GetName()]));changes.append(dict(action='move_group',name=g.GetName(),delta=plan['moves'][g.GetName()]))
s=pcbnew.PCB_SHAPE(b);s.SetShape(pcbnew.SHAPE_T_POLY);s.SetLayer(pcbnew.F_Cu);s.SetFilled(True);s.SetWidth(0);s.SetNet(b.FindNet('GND'));poly=pcbnew.SHAPE_POLY_SET();poly.NewOutline()
for v in plan['guard']:poly.Append(pt(v))
s.SetPolyShape(poly);b.Add(s);ids[s.m_Uuid.AsString()]=str(uuid.uuid5(uuid.NAMESPACE_URL,'stratolink-rf-front-guard-20261014'));changes.append(dict(action='ground_guard',uuid=ids[s.m_Uuid.AsString()],net='GND'))
v=pcbnew.PCB_VIA(b);v.SetPosition(pt(plan['via']));v.SetWidth(500000);v.SetDrill(300000);v.SetViaType(next(t for t in b.GetTracks()if isinstance(t,pcbnew.PCB_VIA)).GetViaType());v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetNet(b.FindNet('GND'));b.Add(v);ids[v.m_Uuid.AsString()]=str(uuid.uuid5(uuid.NAMESPACE_URL,'stratolink-rf-front-guard-via-20261014'));changes.append(dict(action='ground_via',uuid=ids[v.m_Uuid.AsString()],at=plan['via']))
for z in b.Zones():z.UnFill()
pcbnew.SaveBoard(str(p),b);raw=p.read_text()
for a,c in ids.items():raw=raw.replace(a,c)
p.write_text(raw);(p.parent/'front-guard-changes.json').write_text(json.dumps(changes,indent=2)+'\n')
