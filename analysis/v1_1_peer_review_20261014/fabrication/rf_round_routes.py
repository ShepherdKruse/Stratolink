#!/usr/bin/env python3
"""Local route smoothing on frozen RF candidate, never canonical CAD."""
from pathlib import Path
import pcbnew,wx,math,json,hashlib,uuid,sys
p=Path(sys.argv[1]).resolve();assert '/ai-working/scratch/' in str(p)
source=hashlib.sha256(p.read_bytes()).hexdigest();assert source=='af8b32d61756642c1f63b12c7220c10bc17c62dec1fed5c53bf5796f92ab08ec'
app=wx.App(False);b=pcbnew.LoadBoard(str(p));ids={};ledger=[];held=[]
def xy(q):return[q.x/1e6,q.y/1e6]
def pt(q):return pcbnew.VECTOR2I(round(q[0]*1e6),round(q[1]*1e6))
def add(obj,name):
 stable=str(uuid.uuid5(uuid.NAMESPACE_URL,'stratolink-rf-round-20261014/'+name));ids[obj.m_Uuid.AsString()]=stable;b.Add(obj)
 return stable
def track(name,net,layer,width,a,c):
 if math.dist(a,c)<1e-7:return
 t=pcbnew.PCB_TRACK(b);t.SetStart(pt(a));t.SetEnd(pt(c));t.SetWidth(round(width*1e6));t.SetLayer(layer);t.SetNet(b.FindNet(net));uid=add(t,name)
 ledger.append(dict(action='track',name=name,uuid=uid,net=net,width=width,layer=b.GetLayerName(layer),start=a,end=c))
def smooth(name,net,layer,width,points,radius):
 current=points[0]
 for i in range(1,len(points)-1):
  a,c,d=points[i-1:i+2]
  def unit(v):
   n=math.hypot(*v);return(v[0]/n,v[1]/n)
  u=unit((c[0]-a[0],c[1]-a[1]));v=unit((d[0]-c[0],d[1]-c[1]));phi=math.acos(max(-1,min(1,u[0]*v[0]+u[1]*v[1])))
  if phi<1e-5:continue
  r=min(radius,.40*math.dist(a,c)/math.tan(phi/2),.40*math.dist(c,d)/math.tan(phi/2))
  tangent=r*math.tan(phi/2);n=unit((v[0]-u[0],v[1]-u[1]))
  start=(c[0]-u[0]*tangent,c[1]-u[1]*tangent);end=(c[0]+v[0]*tangent,c[1]+v[1]*tangent)
  mid=(c[0]+n[0]*(r/math.cos(phi/2)-r),c[1]+n[1]*(r/math.cos(phi/2)-r))
  track(name+'-line'+str(i),net,layer,width,current,start)
  arc=pcbnew.PCB_ARC(b);arc.SetStart(pt(start));arc.SetMid(pt(mid));arc.SetEnd(pt(end));arc.SetWidth(round(width*1e6));arc.SetLayer(layer);arc.SetNet(b.FindNet(net));uid=add(arc,name+'-arc'+str(i));ledger.append(dict(action='arc',name=name,uuid=uid,net=net,width=width,layer=b.GetLayerName(layer),start=start,mid=mid,end=end,radius_mm=r));current=end
 track(name+'-end',net,layer,width,current,points[-1])
c5=json.loads((p.parent/'c5-changes.json').read_text());names=['rail-gap','scl-side','cap-vbat','balance-vbat','cap-gnd-top','cap-gnd-bottom','u3-ground-pad5','mid-front','mid-cap']
remove={q['uuid'] for q in c5 if q['action']=='add_track' and any(q['name'].startswith(n) for n in names)}
# Replace obsolete .38 mm rail tail and .15 mm balance-sense tail as complete
# original segments, preserving all terminal branch connections and widths.
remove|={'ff8f1a98-3ca9-401e-9302-5b81bbc82365','ed3c2424-a6ad-5bae-9ba7-e3d94993ba1c'}
for t in list(b.GetTracks()):
 if t.m_Uuid.AsString() in remove:
  ledger.append(dict(action='remove_track',uuid=t.m_Uuid.AsString(),net=t.GetNetname(),start=xy(t.GetStart()),end=xy(t.GetEnd()),width=t.GetWidth()/1e6));held.append(t);b.Remove(t)
B=pcbnew.B_Cu;F=pcbnew.F_Cu
smooth('rail','+3.3V',B,.38,[(69.07569,44.041),(68.4,44.041),(68.4,49.1),(66.667,50.833),(66.667,51.322)],.35)
smooth('scl','SCL',B,.25,[(72.912,44.068),(71.8,45.18),(71.8,48.3),(70.197,49.903),(70.197,50.736)],.25)
smooth('vbat','/VBAT',B,.5,[(63.497,43.574),(63.175,43.896),(63.175,46.207)],.25)
smooth('balance-vbat','/VBAT',B,.15,[(59.65,43.3),(59.65,43.574),(63.497,43.574)],.15)
smooth('cap-gnd-top','GND',B,.35,[(71.280903,42.782097),(70.175,43.888),(70.175,46.207)],.25)
smooth('cap-gnd-bottom','GND',B,.25,[(69.15,48.65),(70.175,47.733),(70.175,46.207)],.25)
smooth('u3-ground-pad5','GND',F,.25,[(70.287,48.414001),(69.385999,48.414001),(69.15,48.65)],.15)
smooth('mid-front','/SC_MID',F,.15,[(62.8,42.8),(62.2,43.4),(62.2,49.25)],.25)
smooth('mid-cap','/SC_MID',B,.15,[(62.2,49.25),(64.8,49.25),(65.3,48.75),(66.665,48.75),(66.665,46.207)],.25)
f=next(f for f in b.GetFootprints() if f.GetReference()=='AE2')
for model in f.Models():
 if 'Stratolink_Wire_48mm' in model.m_Filename:
  before=[model.m_Offset.x,model.m_Offset.y,model.m_Offset.z];assert abs(model.m_Offset.z-.15)<1e-9;offset=model.m_Offset;offset.z=.25;model.m_Offset=offset;ledger.append(dict(action='model_nominal_standoff',ref='AE2',model=model.m_Filename,before=before,after=[0,-.2,.25]))
lib=p.parent/'lib/Stratolink_GNSS_Wire_PTH_D1p0.kicad_mod';assert not (p.parent/'lib').is_symlink()
s=lib.read_text();assert '(xyz 0 -0.2 0.15)' in s;s=s.replace('(xyz 0 -0.2 0.15)','(xyz 0 -0.2 0.25)');lib.write_text(s)
for z in b.Zones():z.UnFill()
pcbnew.SaveBoard(str(p),b);s=p.read_text()
for a,c in ids.items():s=s.replace(a,c)
if '(xyz 0 -0.2 0.15)' in s:
 assert s.count('(xyz 0 -0.2 0.15)')==1;s=s.replace('(xyz 0 -0.2 0.15)','(xyz 0 -0.2 0.25)')
assert s.count('(xyz 0 -0.2 0.25)')==1
p.write_text(s);(p.parent/'rounding-ledger.json').write_text(json.dumps(dict(source_sha256=source,changes=ledger),indent=2)+'\n')
print('rounded',len(ledger))
