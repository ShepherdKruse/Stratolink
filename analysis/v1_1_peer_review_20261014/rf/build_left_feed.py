#!/usr/bin/env python3
"""Build isolated left-feed candidate. Does not touch canonical CAD or Git."""
from pathlib import Path
import hashlib,json,shutil,uuid,sys,math,subprocess,argparse
import pcbnew,wx
ROOT=Path(__file__).resolve().parents[3]; HERE=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source',type=Path,default=Path.home()/'Repositories/ai-working/scratch/stratolink-peer-review-20261014/fabrication/copper-final4')
parser.add_argument('--output',type=Path,default=Path.home()/'Repositories/ai-working/scratch/stratolink-peer-review-20261014/rf-left-feed-reproduced')
parser.add_argument('--cap-patch',type=Path,default=HERE/'route_c5.py')
args=parser.parse_args();SOURCE=args.source.resolve();OUT=args.output.resolve()
assert '/ai-working/scratch/'in str(OUT),'Use isolated AI scratch output.'
EXPECTED='4fcdb39b8cc7936295f64ae9f5e1acd4acd01e144cd21e9076f681c23c0e2b54'
assert hashlib.sha256((SOURCE/'stratolink.kicad_pcb').read_bytes()).hexdigest()==EXPECTED
assert not OUT.exists(), "Output must be a fresh isolated folder"
OUT.mkdir(parents=True)
for fn in ['stratolink.kicad_pcb','stratolink.kicad_pro','stratolink.kicad_dru','stratolink.kicad_sch','fp-lib-table','sym-lib-table']:
 shutil.copy2(SOURCE/fn,OUT/fn)
for fn in ['lib','3d']:
 shutil.copytree(SOURCE/fn,OUT/fn,symlinks=False)
# Apply the independently reviewed C5 relocation before constructing the RF route.
# This avoids letting obsolete SC_MID vias touch the new feed during native load.
cap_patch=args.cap_patch.resolve()
if not (OUT/'lib').is_symlink():shutil.copy2(SOURCE/'lib/Stratolink_v1p1_C5_DMF4B5R5G105M3DTA0.kicad_mod',OUT/'lib/Stratolink_v1p1_C5_DMF4B5R5G105M3DTA0.kicad_mod')
subprocess.run([sys.executable,str(cap_patch),'--pcb',str(OUT/'stratolink.kicad_pcb')],check=True)
# Strip saved fills before the first native load; merely UnFill() after load leaves
# a connectivity cache that can infer stale via nets when moved pads are saved.
p=OUT/'stratolink.kicad_pcb';raw=p.read_text()
while '(filled_polygon' in raw:
 start=raw.index('(filled_polygon');depth=0;quoted=False;escaped=False
 for end in range(start,len(raw)):
  ch=raw[end]
  if quoted:
   if escaped:escaped=False
   elif ch=='\\':escaped=True
   elif ch=='"':quoted=False
  elif ch=='"':quoted=True
  elif ch=='(':depth+=1
  elif ch==')':
   depth-=1
   if depth==0:break
 raw=raw[:start]+raw[end+1:]
p.write_text(raw)
app=wx.App(False);b=pcbnew.LoadBoard(str(OUT/'stratolink.kicad_pcb'));changes=[];keep_removed=[]
original_nets={x.m_Uuid.AsString():x.GetNetname()for x in b.GetTracks()}
for z in b.Zones():z.UnFill()
fps={f.GetReference():f for f in b.GetFootprints()}
THROUGH=next(t for t in b.GetTracks() if isinstance(t,pcbnew.PCB_VIA)).GetViaType()
def pt(p):return pcbnew.VECTOR2I(round(p[0]*1e6),round(p[1]*1e6))
def ident(name):return pcbnew.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,'stratolink/rf-left-feed/'+name)))
def net(name):return b.FindNet(name)
def record(action,**kw):changes.append(dict(action=action,**kw))
def track(name,points,netname,width,layer=pcbnew.F_Cu):
 for n,(a,c) in enumerate(zip(points,points[1:])):
  t=pcbnew.PCB_TRACK(b);t.SetStart(pt(a));t.SetEnd(pt(c));t.SetWidth(round(width*1e6));t.SetLayer(layer);t.SetNet(net(netname));b.Add(t)
  record('track',uuid=t.m_Uuid.AsString(),net=netname,width=width,layer=b.GetLayerName(layer),start=a,end=c)
def via(name,p,netname):
 v=pcbnew.PCB_VIA(b);v.SetPosition(pt(p));v.SetWidth(500000);v.SetDrill(300000);v.SetViaType(THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetNet(net(netname));b.Add(v)
 record('via',uuid=v.m_Uuid.AsString(),net=netname,at=p);return v
def move(ref,xy,angle=None):
 f=fps[ref];old=[v/1e6 for v in f.GetPosition()];oldangle=f.GetOrientationDegrees();f.SetPosition(pt(xy))
 if angle is not None:f.SetOrientationDegrees(angle)
 record('footprint',ref=ref,before=old,after=xy,before_angle=oldangle,angle=f.GetOrientationDegrees())
move('C5',(66.675,64.707));move('AE2',(55.3,47.85),180);move('D3',(58.0,45.05),270)
# Remove complete obsolete antenna routes and complete SC_MID interconnect;
# the latter is reconstructed shorter above the RF corridor.
ground_remove={'7b10dc8a-bb51-41f4-a18b-e886d8f00eeb','f21c8730-8d40-4c84-bd82-d97f3cad6e3a','80d817b0-8068-4282-b388-746a7bb3f102','17fb1787-ef6a-426b-a805-b3bc22ad3537','66e770e2-c219-43c9-832b-07ea7422007f','bab03811-1f7b-457e-a7ff-e73d9871517f'}
vbat_remove={'ca4dd144-66af-43ac-8788-94f13488f846','dfe1229e-4726-47ef-96bb-9ef156d9afa4',
 '342c8715-b55e-5543-843e-da1747534068','45427562-abaa-5366-a11d-242da89831f3','5acec003-6cea-5a20-8dcf-1e5a4f6c9879','ee2bbc75-1410-59f9-8c95-7e5259588803'}
vbat_remove=set() # C5 patch owns all original VBAT and midpoint edits.
ground_remove.update({'ecd0f474-83cd-5ecd-8549-569a8af7fc4d','07db5309-9c1f-43f6-a043-1a4cd67ace31','79671340-7dee-45f1-b2a9-275b644c65f7','c20ca163-c0f9-4bd8-a859-3b9994b9964a','31711835-02ce-4524-885d-37fd4bd7a217','e57d7f71-2278-444f-995f-156723a1a4cb','761d094b-2bca-4868-b091-940374427bf3','f5c11b7c-8c29-4aeb-935d-490d8be467dd'})
for t in list(b.GetTracks()):
 uid=t.m_Uuid.AsString()
 if t.GetNetname() in ['Net-(AE2-A)'] or uid in ground_remove|vbat_remove:
  record('remove_track',uuid=uid,net=t.GetNetname());keep_removed.append(t);b.Remove(t)

# Local cleanup polygons belonging to old RF branches must follow their removed routes.
for shape in list(b.GetDrawings()):
 if isinstance(shape,pcbnew.PCB_SHAPE) and shape.GetNetname()=='Net-(AE2-A)':
  record('remove_old_rf_fillet',uuid=shape.m_Uuid.AsString());keep_removed.append(shape);b.Remove(shape)
# Both original copper label groups remain unchanged.
def smooth_track(name,points,netname,width,radius=.35,layer=pcbnew.F_Cu):
 current=points[0]
 for i in range(1,len(points)-1):
  a,c,d=points[i-1:i+2]
  def unit(v):
   n=math.hypot(*v);return(v[0]/n,v[1]/n)
  u=unit((c[0]-a[0],c[1]-a[1]));v=unit((d[0]-c[0],d[1]-c[1]))
  phi=math.acos(max(-1,min(1,u[0]*v[0]+u[1]*v[1])))
  tangent=radius*math.tan(phi/2);n=unit((v[0]-u[0],v[1]-u[1]))
  start=(c[0]-u[0]*tangent,c[1]-u[1]*tangent);end=(c[0]+v[0]*tangent,c[1]+v[1]*tangent)
  mid=(c[0]+n[0]*(radius/math.cos(phi/2)-radius),c[1]+n[1]*(radius/math.cos(phi/2)-radius))
  track(name+'-line'+str(i),[current,start],netname,width,layer)
  arc=pcbnew.PCB_ARC(b);arc.SetStart(pt(start));arc.SetMid(pt(mid));arc.SetEnd(pt(end));arc.SetWidth(round(width*1e6));arc.SetLayer(layer);arc.SetNet(net(netname));b.Add(arc)
  record('arc',uuid=arc.m_Uuid.AsString(),net=netname,width=width,start=start,mid=mid,end=end,layer=b.GetLayerName(layer));current=end
 track(name+'-end',[current,points[-1]],netname,width,layer)
# Controlled-impedance target is conditional on actual stackup and local planes.
smooth_track('rf-main',[(55.3,47.85),(57.4,45.75),(59.2,45.75),(59.836,45.114),(60.787001,45.114001)],'Net-(AE2-A)',.45)
track('c10-ground',[(58.306,46.787),(59.2,46.787),(59.773,46.214),(60.787001,46.214001)],'GND',.25)
track('d3-ground',[(58.0,44.35),(59.5,44.35)],'GND',.25)
for name,xy in [('rf-ground-upper-right',(59.5,44.35)),('rf-ground-lower',(55.1,49.15)),('rf-ground-lower-right',(59.2,46.787))]:via(name,xy,'GND')
for ref,pinnums in [('U3',{'10','12'}),('D3',{'1'})]:
 for p in fps[ref].Pads():
  if p.GetNumber()in pinnums:
   old=p.GetLocalZoneConnection();p.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL);record('pad_zone_connection',ref=ref,pin=p.GetNumber(),before=int(old),after=int(p.GetLocalZoneConnection()))
for layer in [pcbnew.F_Cu,pcbnew.B_Cu]:
 z=pcbnew.ZONE(b);z.SetNet(net('GND'));z.SetLayer(layer);z.SetAssignedPriority(5);z.SetLocalClearance(150000);z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL);z.SetMinThickness(150000)
 poly=z.Outline();poly.NewOutline()
 boundary=([(53.5,47.0),(55.8,47.0),(57.6,45.2),(57.6,43.6),(62.3,43.6),(62.3,50.3),(53.5,50.3)] if layer==pcbnew.F_Cu else [(54.45,43.6),(61.8,43.6),(61.8,49.5),(54.45,49.5)])
 for p in boundary:poly.Append(pt(p))
 b.Add(z);record('local_ground_zone',uuid=z.m_Uuid.AsString(),layer=b.GetLayerName(layer),clearance_mm=.15)
note=pcbnew.PCB_TEXT(b);note.SetLayer(pcbnew.F_Fab);note.SetText('GNSS: 48 mm straight wire LEFT from feed; tune assembled payload');note.SetTextSize(pt((.8,.8)));note.SetTextThickness(120000);note.SetPosition(pt((29,42)));b.Add(note);record('assembly_note',uuid=note.m_Uuid.AsString())
b.BuildConnectivity()
actual={x.m_Uuid.AsString():x.GetNetname()for x in b.GetTracks()}
for uid,n in original_nets.items():
 if uid in actual:assert actual[uid]==n,(uid,n,actual[uid])
for c in changes:
 if c['action']in['track','arc','via']:assert actual[c['uuid']]==c['net'],c
pcbnew.SaveBoard(str(OUT/'stratolink.kicad_pcb'),b)
# Native SWIG UUID is readonly: deterministically normalize only new object IDs
# in the saved native text, including references to those exact IDs.
raw=(OUT/'stratolink.kicad_pcb').read_text()
for index,c in enumerate(changes):
 if c['action']in['track','arc','via','local_ground_zone','assembly_note']:
  old=c['uuid'];new=str(uuid.uuid5(uuid.NAMESPACE_URL,'stratolink/rf-left-feed/'+str(index)+'/'+c['action']));raw=raw.replace(old,new);c['uuid']=new
(OUT/'stratolink.kicad_pcb').write_text(raw)
record('courtyard_margin',refs=['D3','C10'],minimum_nominal_mm=.057,meaning='Existing courtyard edge separation; actual body/land clearances reviewed separately')
record('ae2_model',path='${KIPRJMOD}/lib/Stratolink_Wire_48mm_D0p321_Nominal.step',internal_transform_unchanged=True,footprint_rotation_before=90,footprint_rotation_after=180,radiator_length_mm=48,direction='left',diameter_nominal_mm=.321)
record('candidate_hash_before_refill',sha256=hashlib.sha256((OUT/'stratolink.kicad_pcb').read_bytes()).hexdigest())
(OUT/'changes.json').write_text(json.dumps({'source_sha256':EXPECTED,'changes':changes},indent=2)+'\n')
assert hashlib.sha256((SOURCE/'stratolink.kicad_pcb').read_bytes()).hexdigest()==EXPECTED
print(OUT)
