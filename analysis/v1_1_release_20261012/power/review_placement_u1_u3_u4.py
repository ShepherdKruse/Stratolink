#!/usr/bin/env python3
"""Read canonical KiCad numbered lands and compare exported CPL centers. No CAD writes."""
from pathlib import Path
import csv, hashlib, json
import wx, pcbnew
app=wx.App(False)
root=Path(__file__).resolve().parents[3]
pcb=root/'hardware/pcb/stratolink.kicad_pcb'
cpl=root/'hardware/gerbers/v1.1-pilot/CPL-stratolink.csv'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
before=sha(pcb);board=pcbnew.LoadBoard(str(pcb))
rows={r['Designator']:r for r in csv.DictReader(cpl.open())}
result={}
for fp in board.GetFootprints():
 ref=fp.GetReference()
 if ref not in ['U1','U3','U4']:continue
 pads=[p for p in fp.Pads() if p.GetAttribute()==pcbnew.PAD_ATTRIB_SMD]
 bounds=[p.GetBoundingBox() for p in pads]
 l=min(b.GetLeft() for b in bounds)/1e6;r=max(b.GetRight() for b in bounds)/1e6
 t=min(b.GetTop() for b in bounds)/1e6;b=max(b.GetBottom() for b in bounds)/1e6
 center=[(l+r)/2,(t+b)/2]
 points={p.GetNumber():dict(x=p.GetPosition().x/1e6,y=p.GetPosition().y/1e6,net=p.GetNetname()) for p in pads}
 delta=[float(rows[ref]['Mid X'])-center[0],-float(rows[ref]['Mid Y'])-center[1]]
 assert all(abs(x)<.000003 for x in delta),(ref,delta)
 result[ref]=dict(layer=board.GetLayerName(fp.GetLayer()),native_angle=fp.GetOrientationDegrees(),anchor=[fp.GetPosition().x/1e6,fp.GetPosition().y/1e6],copper_smd_bounds=[l,t,r,b],center=center,numbered_pad_centers=points,cpl=rows[ref],cpl_center_error_mm=delta)
assert sha(pcb)==before
out=dict(status='CENTER_AND_NUMBERED_PAD_CHECK_PASS',pcb_sha256=before,cpl_sha256=sha(cpl),coordinate_convention='Canonical board X right/Y down; bottom component-side north-up view mirrors X only. CPL X is global board X, CPL Y=-boardY; bottom CPL X is not mirrored.',parts=result,source_verification='See placement-u1-u3-u4-review.md for primary-source orientation review and supplier-preview caveats.')
Path(__file__).with_name('placement-u1-u3-u4-native.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({r:{k:v for k,v in d.items() if k!='numbered_pad_centers'} for r,d in result.items()},indent=2))
