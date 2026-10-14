#!/usr/bin/env python3
"""Local copper-only prototype on an isolated copy; never edits canonical CAD."""
from pathlib import Path
import pcbnew,wx,uuid,json,hashlib,sys
app=wx.App(False)
p=Path(sys.argv[1]).resolve();assert '/ai-working/scratch/' in str(p)
b=pcbnew.LoadBoard(str(p));source=hashlib.sha256(p.read_bytes()).hexdigest()
def xy(p):return [p.x/1e6,p.y/1e6]
def uid(n):return str(uuid.uuid5(uuid.NAMESPACE_URL,'stratolink-peer-copper-20261014/'+n))
assert source=='9d63500a087ef8d345c2337942106e6704d32ded953846883454bfad718adf6c'
changes=[]; identities={}
def track(n,net,layer,width,start,end):
 t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I(round(start[0]*1e6),round(start[1]*1e6)));t.SetEnd(pcbnew.VECTOR2I(round(end[0]*1e6),round(end[1]*1e6)));t.SetWidth(round(width*1e6));t.SetLayer(layer);t.SetNet(b.FindNet(net));identities[t.m_Uuid.AsString()]=uid(n);b.Add(t);changes.append(dict(action='add',name=n,uuid=uid(n),net=net,layer=b.GetLayerName(layer),width=width,start=start,end=end))
# Explicit conductor avoids near-tangent pad/via copper contact.
track('u8-explicit-pad4-via','/SC_BAL_OUT',pcbnew.B_Cu,.35,(56.7875,35.15),(57.5,35.65))
# Close local ground crescent; this is outside the PA8 via clearance moat.
track('ground-crescent','GND',pcbnew.F_Cu,.25,(70.3,62.05),(70.3,62.7))
# Fill only four 53um enclosed voids in the front GND union around U1.21.
track('u1-front-ground-diagonal1','GND',pcbnew.F_Cu,.25,(66.940998,37.564999),(67.440998,38.064999))
track('u1-front-ground-diagonal2','GND',pcbnew.F_Cu,.25,(67.440998,37.564999),(66.940998,38.064999))
# Fill the 32um enclosed void in the buck OUTPUT rail, not its switch node.
track('l2-output-void','+3.3V',pcbnew.B_Cu,.15,(71.15,41.65),(71.25,41.75))
for t in b.GetTracks():
 if t.m_Uuid.AsString()=='f950083f-9c44-5581-b006-dd929a7699ef':
  assert t.GetNetname()=='GND' and t.GetWidth()==150000
  changes.append(dict(action='width',uuid=t.m_Uuid.AsString(),before_mm=.15,after_mm=.20,net=t.GetNetname(),start=xy(t.GetStart()),end=xy(t.GetEnd())))
  t.SetWidth(200000)
pcbnew.SaveBoard(str(p),b)
s=p.read_text()
for old,new in identities.items():s=s.replace(old,new)
p.write_text(s)
(p.parent/'copper-fix-changes.json').write_text(json.dumps(dict(source_sha256=source,pcb_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),changes=changes),indent=2)+'\n')
print(json.dumps(changes,indent=2))
