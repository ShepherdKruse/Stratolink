#!/usr/bin/env python3
"""Read-only native artwork polygons for identifying geometry-screen candidates."""
from pathlib import Path
import hashlib,json,sys
import pcbnew,wx
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'analysis/v1_1_solar_attachments_20261012/materials'))
from extract_native import contours
app=wx.App(False);p=ROOT/'hardware/pcb/stratolink.kicad_pcb';raw=p.read_bytes();b=pcbnew.LoadBoard(str(p));rows=[]
for s in b.GetDrawings():
 if s.GetLayer() not in [pcbnew.F_Cu,pcbnew.B_Cu]:continue
 poly=pcbnew.SHAPE_POLY_SET();s.TransformShapeToPolygon(poly,s.GetLayer(),0,2000,pcbnew.ERROR_OUTSIDE);poly.Simplify()
 rows.append({'kind':s.GetClass(),'uuid':s.m_Uuid.AsString(),'layer':s.GetLayerName(),'text':s.GetText() if isinstance(s,pcbnew.PCB_TEXT) else None,'polygons':contours(poly)})
assert p.read_bytes()==raw
(HERE/'artwork-geometry.json').write_text(json.dumps({'source_sha256':hashlib.sha256(raw).hexdigest(),'items':rows},separators=(',',':'))+'\n')
print(len(rows))
