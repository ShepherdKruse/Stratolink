#!/usr/bin/env python3
"""Read canonical U7 pad/mask and nearby copper geometry, without saving CAD."""
from pathlib import Path
import hashlib,json
import pcbnew,wx
H=Path(__file__).resolve().parent;ROOT=H.parents[2]
p=ROOT/'hardware/pcb/stratolink.kicad_pcb';source=p.read_bytes();app=wx.App(False);b=pcbnew.LoadBoard(str(p));fp=next(f for f in b.GetFootprints() if f.GetReference()=='U7')
def poly(item,expansion=0):
 q=pcbnew.SHAPE_POLY_SET()
 if isinstance(item,pcbnew.PAD):
  # Gerber keeps roundrect radius ratio when expanding aperture dimensions.
  # A polygon offset would incorrectly add the full margin to corner radius.
  item=pcbnew.PAD(item);sz=item.GetSize();grow=round(expansion*2e6);item.SetSize(pcbnew.VECTOR2I(sz.x+grow,sz.y+grow))
 item.TransformShapeToPolygon(q,pcbnew.F_Cu,0,100,pcbnew.ERROR_OUTSIDE)
 def chain(c):return [[c.CPoint(i).x/1e6,c.CPoint(i).y/1e6] for i in range(c.PointCount())]
 return [{'shell':chain(q.Outline(i)),'holes':[chain(q.Hole(i,j)) for j in range(q.HoleCount(i))]} for i in range(q.OutlineCount())]
def mm(v):return [v.x/1e6,v.y/1e6]
pads=[]
for pad in fp.Pads():
 pads.append(dict(number=pad.GetNumber(),net=pad.GetNetname(),at_mm=mm(pad.GetPosition()),size_mm=mm(pad.GetSize()),uuid=pad.m_Uuid.AsString(),rotation_deg=pad.GetOrientationDegrees(),existing_margin_mm=pad.GetSolderMaskExpansion(pcbnew.F_Mask)/1e6,alternatives={str(m):poly(pad,m) for m in [.102,.05,.025,.015,.005,0,-.005]}))
others=[]
for item in b.GetTracks():
 if not item.IsOnLayer(pcbnew.F_Cu):continue
 others.append(dict(type='via' if isinstance(item,pcbnew.PCB_VIA) else 'track',net=item.GetNetname(),uuid=item.m_Uuid.AsString(),polygons=poly(item)))
for f in b.GetFootprints():
 if f.GetReference()=='U7':continue
 for pad in f.Pads():
  if pad.IsOnLayer(pcbnew.F_Cu):others.append(dict(type='pad',ref=f.GetReference(),number=pad.GetNumber(),net=pad.GetNetname(),uuid=pad.m_Uuid.AsString(),polygons=poly(pad)))
out=dict(source_sha256=hashlib.sha256(source).hexdigest(),kicad=pcbnew.GetBuildVersion(),method='Native KiCad pad polygon geometry; 0.0001 mm maximum outward approximation error; mask apertures use expanded dimensions and preserved roundrect radius ratio, matching actual Gerber aperture macros. Foreign-net copper is screened, intentional same-net entry traces excluded.',pads=pads,foreign_copper=others)
assert p.read_bytes()==source
(H/'geometry-native.json').write_text(json.dumps(out,separators=(',',':'))+'\n')
print(out['source_sha256'])
