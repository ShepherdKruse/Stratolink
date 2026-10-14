"""Read-only in-memory U3 placement screen. Never save a candidate or change source."""
from pathlib import Path
import sys,json,hashlib
import pcbnew,wx
ROOT=Path(__file__).resolve().parents[3]; HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'analysis/v1_1_solar_attachments_20261012/materials'))
from extract_native import contours
p=ROOT/'hardware/pcb/stratolink.kicad_pcb';raw=p.read_bytes();app=wx.App(False);b=pcbnew.LoadBoard(str(p))
out={'source_sha256':hashlib.sha256(raw).hexdigest(),'front_footprints':{},'front_artwork':[]}
for f in b.GetFootprints():
 if f.GetLayer()!=pcbnew.F_Cu or f.GetReference()=='U3':continue
 f.BuildCourtyardCaches()
 out['front_footprints'][f.GetReference()]={'courtyard':contours(f.GetCourtyard(pcbnew.F_CrtYd)),'value':f.GetValue()}
for t in b.GetDrawings():
 if not t.IsOnLayer(pcbnew.F_Cu):continue
 poly=pcbnew.SHAPE_POLY_SET()
 if isinstance(t,pcbnew.PCB_TEXT):t.TransformTextToPolySet(poly,0,2000,pcbnew.ERROR_OUTSIDE)
 else:t.TransformShapeToPolygon(poly,pcbnew.F_Cu,0,2000,pcbnew.ERROR_OUTSIDE)
 out['front_artwork'].append({'uuid':t.m_Uuid.AsString(),'type':type(t).__name__,'polygons':contours(poly)})
f=next(f for f in b.GetFootprints()if f.GetReference()=='U3')
f.SetPosition(pcbnew.VECTOR2I(59582000,44150000));f.SetOrientationDegrees(90);f.BuildCourtyardCaches()
out['rotated_u3']={'at':[59.582,44.15],'angle':90,'courtyard':contours(f.GetCourtyard(pcbnew.F_CrtYd)),'pads':[]}
for pad in f.Pads():
 poly=pcbnew.SHAPE_POLY_SET();pad.TransformShapeToPolygon(poly,pcbnew.F_Cu,0,2000,pcbnew.ERROR_OUTSIDE)
 out['rotated_u3']['pads'].append({'pin':pad.GetNumber(),'net':pad.GetNetname(),'at':[v/1e6 for v in pad.GetPosition()],'polygons':contours(poly)})
assert p.read_bytes()==raw
(HERE/'placement-native.json').write_text(json.dumps(out,separators=(',',':'))+'\n')
print('Read-only placement screen saved; source unchanged')
