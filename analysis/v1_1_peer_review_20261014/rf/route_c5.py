from pathlib import Path
import pcbnew,wx,shutil,json,uuid,hashlib,argparse
ap=argparse.ArgumentParser();ap.add_argument('--pcb',type=Path,required=True);args=ap.parse_args()
p=args.pcb.resolve();assert '/ai-working/' in str(p)
source_sha256=hashlib.sha256(p.read_bytes()).hexdigest()
assert source_sha256=='4fcdb39b8cc7936295f64ae9f5e1acd4acd01e144cd21e9076f681c23c0e2b54',source_sha256
H=p.parent
s=p.read_text()
while '(filled_polygon' in s:
 st=s.index('(filled_polygon');depth=0
 for end in range(st,len(s)):
  if s[end]=='(':depth+=1
  elif s[end]==')':
   depth-=1
   if not depth:break
 s=s[:st]+s[end+1:]
p.write_text(s);app=wx.App(False);b=pcbnew.LoadBoard(str(p));changes=[];identities={};held=[]
def pt(x):return pcbnew.VECTOR2I(round(x[0]*1e6),round(x[1]*1e6))
def xy(x):return [x.x/1e6,x.y/1e6]
def stable(obj,name):identities[obj.m_Uuid.AsString()]=str(uuid.uuid5(uuid.NAMESPACE_URL,'stratolink-c5-reroute-20261014/'+name))
def add(name,net,width,layer,points):
 for i,(a,c) in enumerate(zip(points,points[1:])):
  t=pcbnew.PCB_TRACK(b);t.SetStart(pt(a));t.SetEnd(pt(c));t.SetWidth(round(width*1e6));t.SetLayer(layer);t.SetNet(b.FindNet(net));b.Add(t);stable(t,name+str(i));changes.append(dict(action='add_track',name=name+str(i),uuid=identities[t.m_Uuid.AsString()],net=net,width=width,layer=b.GetLayerName(layer),start=a,end=c))
def via(name,net,at):
 t=pcbnew.PCB_VIA(b);t.SetPosition(pt(at));t.SetWidth(500000);t.SetDrill(300000);t.SetViaType(next(v for v in b.GetTracks() if isinstance(v,pcbnew.PCB_VIA)).GetViaType());t.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);t.SetNet(b.FindNet(net));b.Add(t);stable(t,name);changes.append(dict(action='add_via',name=name,uuid=identities[t.m_Uuid.AsString()],net=net,at=at))
f=next(f for f in b.GetFootprints() if f.GetReference()=='C5');f.SetPosition(pt((66.675,64.707)));changes.append(dict(action='move_C5',from_mm=[64.875,64.707],to_mm=[66.675,64.707]))
# Maximum 30.5 x 14.5 mm case, plus 0.125 mm controlled manual assembly
# allowance. Pad envelope extends above case and dominates upper boundary.
for g in f.GraphicalItems():
 if g.GetLayer()==pcbnew.B_CrtYd:
  a,c=xy(g.GetStart()),xy(g.GetEnd());old=[a,c]
  def bound(q):return (66.675+(-7.375 if q[0]<66.675 else 7.375),64.707+(-20.375 if q[1]<64.707 else 15.375))
  g.SetStart(pt(bound(a)));g.SetEnd(pt(bound(c)));changes.append(dict(action='courtyard',uuid=g.m_Uuid.AsString(),before=old,after=[xy(g.GetStart()),xy(g.GetEnd())]))

remove={'11de0c41-aa4d-4e27-b6d0-b58a933e695a','341c3179-a551-494a-89c8-a3cada6881c3','8b14279b-46b9-4d32-9dc7-736ab7ef6688','9b634c7e-715b-41e1-8ea4-4eb68b2caac5','cb1d993a-2ee7-4621-a03e-0444baf5ed9d','e8bcafc6-9f42-40d7-b10a-14ee014313d7','ca4dd144-66af-43ac-8788-94f13488f846','dfe1229e-4726-47ef-96bb-9ef156d9afa4','6c7c70c0-3c91-435d-a0c1-dd4b0f00e888','6dcd3b9c-df31-4625-8b9a-bdec1071d766','ab129a02-1a6c-4de2-9d1b-d3ed57edbb98','b3828945-4c9c-4a5d-8dea-a526e7579666','824fdb56-8c55-4686-a22e-ae7827d6c34f','826d6134-6057-4fa0-b7c8-feb8cc768ddb', '342c8715-b55e-5543-843e-da1747534068','45427562-abaa-5366-a11d-242da89831f3','5acec003-6cea-5a20-8dcf-1e5a4f6c9879','ee2bbc75-1410-59f9-8c95-7e5259588803'}
for t in list(b.GetTracks()):
 uid=t.m_Uuid.AsString()
 if uid in remove or t.GetNetname()=='/SC_MID':
  changes.append(dict(action='remove_track',uuid=uid,net=t.GetNetname(),start=xy(t.GetStart()),end=xy(t.GetEnd())));held.append(t);b.Remove(t)
 elif uid in {'9ed60aaf-ea41-4256-bde4-9661188f60ee','4a760ce3-2f6b-4cf9-bd55-4b89f4f8bb06','53f723fc-0789-4808-bc5f-268a7b7cb4b1','96c69d44-16d8-4726-9883-9e2cd56ecd4f'}:
  dest={'9ed60aaf-ea41-4256-bde4-9661188f60ee':(72.15,42.5),'4a760ce3-2f6b-4cf9-bd55-4b89f4f8bb06':(67.6,48.7),'53f723fc-0789-4808-bc5f-268a7b7cb4b1':(69.15,48.65),'96c69d44-16d8-4726-9883-9e2cd56ecd4f':(68.7,50.1)}[uid]
  changes.append(dict(action='move_via',uuid=uid,net=t.GetNetname(),before=xy(t.GetPosition()),after=dest));t.SetPosition(pt(dest))
# Remove old fillets attached to replaced routes, to be regenerated after topology settles.
for t in list(b.GetDrawings()):
 if isinstance(t,pcbnew.PCB_SHAPE) and t.GetNetname() in ['/SC_MID','+3.3V','SCL','/VBAT','GND']:
  bb=t.GetBoundingBox();x,y=bb.GetCenter().x/1e6,bb.GetCenter().y/1e6
  if (64.3<x<72.5 and 43.7<y<51.5) or (57.4<x<58.2 and 44.7<y<45.9):
   changes.append(dict(action='remove_local_fillet',uuid=t.m_Uuid.AsString(),net=t.GetNetname()));held.append(t);b.Remove(t)
add('rail-gap','+3.3V',.38,pcbnew.B_Cu,[(66.985,44.041),(68.4,44.041),(68.4,49.1),(66.667,50.833),(66.667,51.322)])
add('scl-side','SCL',.25,pcbnew.B_Cu,[(72.912,44.068),(71.8,45.18),(71.8,48.3),(70.197,49.903),(70.197,50.736)])
add('cap-vbat','/VBAT',.5,pcbnew.B_Cu,[(63.497,43.574),(63.175,43.896),(63.175,46.207)])
add('balance-vbat','/VBAT',.15,pcbnew.B_Cu,[(59.65,43.85),(59.65,43.574),(63.497,43.574)])
add('cap-gnd-top','GND',.35,pcbnew.B_Cu,[(71.280903,42.782097),(70.175,43.888),(70.175,46.207)])
add('cap-gnd-bottom','GND',.25,pcbnew.B_Cu,[(69.15,48.65),(70.175,47.733),(70.175,46.207)])
add('u3-ground-pad5','GND',.25,pcbnew.F_Cu,[(70.287,48.414001),(69.385999,48.414001),(69.15,48.65)])
via('mid-r26','/SC_MID',(62.8,42.8));via('mid-under-u3','/SC_MID',(62.2,49.25))
add('mid-r26-escape','/SC_MID',.15,pcbnew.B_Cu,[(61.2,43.01),(61.3,43.11),(62.49,43.11),(62.8,42.8)])
add('mid-front','/SC_MID',.15,pcbnew.F_Cu,[(62.8,42.8),(62.2,43.4),(62.2,49.25)])
add('mid-cap','/SC_MID',.15,pcbnew.B_Cu,[(62.2,49.25),(64.8,49.25),(65.3,48.75),(66.665,48.75),(66.665,46.207)])
for z in b.Zones():z.UnFill()
pcbnew.SaveBoard(str(p),b);raw=p.read_text()
for a,c in identities.items():raw=raw.replace(a,c)
p.write_text(raw)
# Local library is copied before its courtyard edit, never edited through a symlink.
lib=p.parent/'lib'
if lib.is_symlink():
 source=lib.resolve();lib.unlink();shutil.copytree(source,lib)
libfile=lib/'Stratolink_v1p1_C5_DMF4B5R5G105M3DTA0.kicad_mod'
s=libfile.read_text();oldlib=hashlib.sha256(s.encode()).hexdigest()
for a,c in [('-8 -21.25','-7.375 -20.375'),('-8 16','-7.375 15.375'),('8 -21.25','7.375 -20.375'),('8 16','7.375 15.375')]:s=s.replace(a,c)
libfile.write_text(s);changes.append(dict(action='library_courtyard',path=str(libfile),before_sha256=oldlib,after_sha256=hashlib.sha256(s.encode()).hexdigest()))
(H/'c5-changes.json').write_text(json.dumps(changes,indent=2)+'\n');print(p)
