#!/usr/bin/env python3
"""Native CAD authoring for the top-feed revision. Final fabrication fillets are separate."""
from pathlib import Path
import hashlib,json,shutil,uuid,sys,math
import pcbnew,wx
import argparse
ROOT=Path(__file__).resolve().parents[3]
ap=argparse.ArgumentParser(description='Build an isolated top-feed PCB revision from the reviewed 8df85 baseline.')
ap.add_argument('--source',type=Path,required=True)
ap.add_argument('--project',type=Path,required=True,help='Strict reviewed project file; user-local relaxed overrides are rejected.')
ap.add_argument('--output',type=Path,required=True)
args=ap.parse_args();BASE=args.source.resolve();OUT=args.output.resolve()
assert OUT != BASE and BASE not in OUT.parents, 'Output must be outside the source project.'
assert not (OUT == ROOT/'hardware' or ROOT/'hardware' in OUT.parents), 'Do not write into canonical hardware.'
assert hashlib.sha256(args.project.read_bytes()).hexdigest()=='915d9f9c4bc8c1eb0866031bf765ff08dc41a7b5bea4fb158ca26c1032ef93cd', 'Use the reviewed strict project.'
EXPECTED='8df85b3e4bdd546ec174bb9d7b9ee9d795d55d486a68e1e853aaf1b871f863d3'
assert hashlib.sha256((BASE/'stratolink.kicad_pcb').read_bytes()).hexdigest()==EXPECTED
assert not OUT.exists(), "Refuse to overwrite a frozen candidate; choose a fresh output folder."
OUT.mkdir()
for fn in ['stratolink.kicad_pcb','stratolink.kicad_sch','stratolink.kicad_dru','fp-lib-table','sym-lib-table']:shutil.copy2(BASE/fn,OUT/fn)
shutil.copy2(args.project,OUT/'stratolink.kicad_pro')
for fn in ['lib','3d']:shutil.copytree(BASE/fn,OUT/fn,symlinks=False)
p=OUT/'stratolink.kicad_pcb';raw=p.read_text()
while '(filled_polygon' in raw:
 start=raw.index('(filled_polygon');depth=0;quoted=False;esc=False
 for end in range(start,len(raw)):
  ch=raw[end]
  if quoted:
   if esc:esc=False
   elif ch=='\\':esc=True
   elif ch=='"':quoted=False
  elif ch=='"':quoted=True
  elif ch=='(':depth+=1
  elif ch==')':
   depth-=1
   if depth==0:break
 raw=raw[:start]+raw[end+1:]
p.write_text(raw);app=wx.App(False);b=pcbnew.LoadBoard(str(p));changes=[];removed=[];fps={f.GetReference():f for f in b.GetFootprints()};oldnets={t.m_Uuid.AsString():t.GetNetname() for t in b.GetTracks()};through=next(t for t in b.GetTracks()if isinstance(t,pcbnew.PCB_VIA)).GetViaType()
def pt(x):return pcbnew.VECTOR2I(round(x[0]*1e6),round(x[1]*1e6))
def xy(p):return(p.x/1e6,p.y/1e6)
def rec(action,**kw):changes.append(dict(action=action,**kw))
def delete(t):rec('remove',uuid=t.m_Uuid.AsString(),net=t.GetNetname());removed.append(t);b.Remove(t)
def track(points,net,width=.15,layer=pcbnew.F_Cu):
 for a,c in zip(points,points[1:]):
  if math.dist(a,c)<1e-5:continue
  t=pcbnew.PCB_TRACK(b);t.SetStart(pt(a));t.SetEnd(pt(c));t.SetWidth(round(width*1e6));t.SetLayer(layer);t.SetNet(b.FindNet(net));b.Add(t);rec('track',uuid=t.m_Uuid.AsString(),net=net,points=[a,c],width=width,layer=b.GetLayerName(layer))
def via(pos,net):
 v=pcbnew.PCB_VIA(b);v.SetPosition(pt(pos));v.SetWidth(500000);v.SetDrill(300000);v.SetViaType(through);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetNet(b.FindNet(net));b.Add(v);rec('via',uuid=v.m_Uuid.AsString(),at=pos,net=net)
def smooth(points,net,width=.15,r=.2,layer=pcbnew.F_Cu):
 current=points[0]
 for i in range(1,len(points)-1):
  a,c,d=points[i-1:i+2]
  def unit(v):
   n=math.hypot(*v);return(v[0]/n,v[1]/n)
  u=unit((c[0]-a[0],c[1]-a[1]));v=unit((d[0]-c[0],d[1]-c[1]));phi=math.acos(max(-1,min(1,u[0]*v[0]+u[1]*v[1])))
  if phi<1e-5:continue
  rad=min(r,.4*math.dist(a,c)/math.tan(phi/2),.4*math.dist(c,d)/math.tan(phi/2));tangent=rad*math.tan(phi/2);n=unit((v[0]-u[0],v[1]-u[1]));start=(c[0]-u[0]*tangent,c[1]-u[1]*tangent);end=(c[0]+v[0]*tangent,c[1]+v[1]*tangent);mid=(c[0]+n[0]*(rad/math.cos(phi/2)-rad),c[1]+n[1]*(rad/math.cos(phi/2)-rad));track([current,start],net,width,layer)
  ar=pcbnew.PCB_ARC(b);ar.SetStart(pt(start));ar.SetMid(pt(mid));ar.SetEnd(pt(end));ar.SetWidth(round(width*1e6));ar.SetLayer(layer);ar.SetNet(b.FindNet(net));b.Add(ar);rec('arc',uuid=ar.m_Uuid.AsString(),net=net,start=start,mid=mid,end=end,width=width,layer=b.GetLayerName(layer));current=end
 track([current,points[-1]],net,width,layer)
def move(ref,pos,angle=None):
 f=fps[ref];rec('move',ref=ref,before=xy(f.GetPosition()),after=pos,before_angle=f.GetOrientationDegrees(),after_angle=f.GetOrientationDegrees() if angle is None else angle);f.SetPosition(pt(pos))
 if angle is not None:f.SetOrientationDegrees(angle)
move('AE2',(62.882,33.218),90);move('L1',(60.603,38.1865));move('D3',(58.8,42.0),0)
# Complete RF/old guard cleanup and quiet-network replacement.
solar_remove={'565c06b7-9582-44f0-a88c-af66fec0f3f0','7ede80ea-e043-4f1d-be89-fb1d451eb73a','b31eff8a-b884-49df-8e32-245c0db06289','30f9387b-6101-4b58-90b6-f944cba6fad5','b55f0878-fc10-4082-90bc-7707c4d2c0bc','17d6f993-3d9b-46b3-ad58-a9fc892fc874','a8b5072c-ca58-4971-bd14-97364fc1e043','f5275c5f-c7b1-49db-bf4a-4d1022d5e45f','68ff3b5b-3b97-492d-98f3-727c63925442','80a79207-0d2b-4ce4-b70b-78970d12fa25','e9bec5b4-88da-45ea-9fa2-1d1c291498d9'}
for t in list(b.GetTracks()):
 uid=t.m_Uuid.AsString();net=t.GetNetname();a=xy(t.GetStart());c=xy(t.GetEnd())
 rm=net in ['Net-(AE2-A)','/SC_BAL_OUT'] or uid in solar_remove or uid in {'cb09c440-db10-5717-8a62-d14623df26b2','0bfcd2d0-e08c-4898-b421-bf19060d510f','839c7715-480e-4339-a257-030433660756','aaab34f8-380c-55ba-a911-c0477b0c3e76','1dad97a1-d2d0-5c74-9948-b124ce28c8dc','d4db4626-2f36-5f70-9f4f-c2358bdf416c'}
 if net=='/VBAT' and max(a[0],c[0])<63 and min(a[1],c[1])<44:rm=True
 if uid=='98e63a09-1f2d-5d9e-8602-85b828231b42':rm=True
 if net=='GND' and (math.dist(a,(58,44.35))<.01 or math.dist(c,(58,44.35))<.01 or math.dist(a,(59.5,44.35))<.01):rm=True
 if rm:delete(t)
for t in list(b.GetTracks()):
 if t.m_Uuid.AsString() in {'37afa236-74ce-472b-9693-ad420388b7b1', '8dd727f3-5cc5-5f06-8558-46e5c8c1602b', 'a34a08fd-10bb-4b4f-b177-137f34dc4faf', '9c0017e8-cf41-4358-a960-ae1c3f003926', '1819afe9-bd05-43d8-a271-633693b4bedb', '8596c57b-3a96-44cf-a676-d38ccaef1053', 'cc1ebe29-cc66-48db-9b8d-f992f6eaeb26', 'c6b4c200-0c9f-41d0-94be-2447f37e183d', '96d0f8c5-cacd-4704-ae1f-fcf30fdd0cd6', 'da78c286-763d-4c08-a516-f5745d1e5dd9', '025e778a-9eb4-4dc9-b548-e9352664b148', 'ed5f67c8-3552-454f-9529-35b6fe329c10', 'd7f4b9b2-2047-4150-a61f-c58dac0a25fc', '2e4b2772-843a-4aa2-ac6f-1edad189e562', '8b581ef7-053c-42a0-b06f-844c189292f3', '74c8c306-2b30-4648-890d-33cc6250e934', '7d19371f-b442-4cc7-90d2-109eb81b8831', '5eb68679-9f84-409e-92a6-c5d5f1bdd2a5', '74d5af21-16b6-4d42-a19a-2869c6730ef9', '56cc68d0-4695-4ea1-83ad-7cba0430de38'}:delete(t)
# Remove copper fillets belonging to removed routes or quiet-net reroutes.
for s in list(b.GetDrawings()):
 if isinstance(s,pcbnew.PCB_SHAPE):
  net=s.GetNetname();uid=s.m_Uuid.AsString();bb=s.GetBoundingBox();rm=net in['Net-(AE2-A)','/SC_BAL_OUT'] or uid=='f5107420-9f61-54b6-889e-abad2b9900fe'
  if net=='/VBAT' and bb.GetRight()/1e6<63 and bb.GetTop()/1e6<44:rm=True
  if rm:delete(s)
 if isinstance(s,pcbnew.PCB_TEXT)and'GNSS: 48 mm straight wire LEFT'in s.GetText():s.SetText('GNSS: 48 mm straight wire UP from top feed; tune assembled payload')
# Shift only L1 terminal connections at their exact shared old terminal centers.
for t in b.GetTracks():
 if t.GetNetname()not in ['+SOLAR','Net-(U1-LBOOST)']:continue
 for method,setter in [('GetStart','SetStart'),('GetEnd','SetEnd')]:
  a=xy(getattr(t,method)())
  if any(math.dist(a,q)<.0001 for q in [(60.103,36.4215),(60.103,39.9515)]):getattr(t,setter)(pt((a[0]+.5,a[1])));rec('terminal_endpoint_shift',uuid=t.m_Uuid.AsString(),endpoint=method,before=a,after=(a[0]+.5,a[1]))
# Shift complete branding groups to open the quiet-network clearance corridor.
for group in b.Groups():
 if group.GetName() in ['Copper label: PICO MAINBOARD V1.1','Copper label: STRATOLINK.ORG']:
  dx=-.6 if 'PICO' in group.GetName() else -.4
  group.Move(pt((dx,0)));rec('move_group',name=group.GetName(),delta=[dx,0])
smooth([(70.827057,31.671),(64.3,31.671),(64.05,31.921),(64.05,34.7),(63.4,35.35),(63.4,38.367),(63.873,38.367)],'+SOLAR',.5,.15,pcbnew.B_Cu)
# Actual RF route, west of L1 and right of rear artwork.
smooth([(60.787001,45.114001),(60.0,45.114001),(59.5,44.614),(59.5,41.25),(58.25,40.0),(58.25,35.95),(58.9,35.3),(58.9,34.2),(59.882,33.218),(62.882,33.218)],'Net-(AE2-A)',.45,.35)
# Output balancing network wraps above the antenna endpoint on the front.
track([(54.5125,37.05),(55.25,37.05),(55.9,36.4),(56.65,36.4),(56.9,35.95)],'/SC_BAL_OUT',.15,pcbnew.B_Cu)
track([(56.7875,35.15),(56.9,35.15),(56.9,35.95)],'/SC_BAL_OUT',.15,pcbnew.B_Cu);via((56.9,35.95),'/SC_BAL_OUT')
smooth([(56.9,35.95),(56.9,33.3),(57.7,32.5),(57.7,31.0),(58.0,30.7),(64.0,30.7),(64.3,31.0),(64.3,34.5),(63.95,34.85),(63.95,41.5)],'/SC_BAL_OUT',.15,.15)
via((63.95,41.5),'/SC_BAL_OUT');smooth([(63.95,41.5),(61.7,41.5),(61.2,41.99)],'/SC_BAL_OUT',.15,.15,pcbnew.B_Cu)
# VBAT's low-current balancer/sense branch, separated from the SC_BAL loop.
track([(56.7875,37.05),(57.2,37.6)],'/VBAT',.15,pcbnew.B_Cu);via((57.2,37.6),'/VBAT')
smooth([(57.2,37.6),(57.45,37.35),(57.45,33.2),(58.1,32.55),(58.1,31.5),(58.3,31.2),(63.7,31.2),(64.0,31.5),(64.0,34.2),(63.4,34.8),(63.4,42.9),(63.5,43.0),(63.5,43.1)],'/VBAT',.15,.15)
via((57.8,33.1),'/VBAT');track([(57.45,33.2),(57.8,33.1)],'/VBAT');track([(57.8,33.1),(57.91,33.9)],'/VBAT',.15,pcbnew.B_Cu)
track([(56.7875,37.05),(56.7875,37.7),(56.08,38.3)],'/VBAT',.15,pcbnew.B_Cu)
via((63.5,43.1),'/VBAT');track([(63.5,43.1),(63.497,43.574)],'/VBAT',.15,pcbnew.B_Cu)
track([(58.1,42.0),(58.0,41.9),(58.0,41.3)],'GND',.25);via((58.0,41.3),'GND')
via((58.7,32.7),'GND')
# Reference fills along the whole new feed, plus later native verification.
for layer in[pcbnew.F_Cu,pcbnew.B_Cu]:
 z=pcbnew.ZONE(b);z.SetNet(b.FindNet('GND'));z.SetLayer(layer);z.SetAssignedPriority(6);z.SetLocalClearance(150000);z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL);z.SetMinThickness(150000);poly=z.Outline();poly.NewOutline()
 for q in[(57.0,30.0),(64.6,30.0),(64.6,46.4),(57.0,46.4)]:poly.Append(pt(q))
 b.Add(z);rec('zone',uuid=z.m_Uuid.AsString(),layer=b.GetLayerName(layer))
b.BuildConnectivity();actual={t.m_Uuid.AsString():t.GetNetname()for t in b.GetTracks()}
for uid,n in oldnets.items():
 if uid in actual:assert actual[uid]==n,(uid,n,actual[uid])
for c in changes:
 if c['action']in['track','arc','via']:assert actual[c['uuid']]==c['net'],c
pcbnew.SaveBoard(str(p),b);raw=p.read_text()
for idx,c in enumerate(changes):
 if c['action']in['track','arc','via','zone']:
  old=c['uuid'];new=str(uuid.uuid5(uuid.NAMESPACE_URL,'stratolink/top-return/'+str(idx)));raw=raw.replace(old,new);c['uuid']=new
p.write_text(raw);(OUT/'changes.json').write_text(json.dumps(dict(source_sha256=EXPECTED,changes=changes),indent=2)+'\n');print(OUT)
