from pathlib import Path
import pcbnew,wx,json,sys
ROOT=Path('/Users/twarn/Repositories/Stratolink');sys.path.insert(0,str(ROOT/'analysis/v1_1_solar_attachments_20261012/materials'));from extract_native import contours
app=wx.App(False);b=pcbnew.LoadBoard(str(ROOT/'hardware/pcb/stratolink.kicad_pcb'));pcbnew.ZONE_FILLER(b).Fill(b.Zones());fp=next(f for f in b.GetFootprints() if f.GetReference()=='U7');output={'at':list(fp.GetPosition()),'angle':fp.GetOrientationDegrees(),'pads':[],'tracks':[],'zones':[]}
for p in fp.Pads():
 poly=pcbnew.SHAPE_POLY_SET();p.TransformShapeToPolygon(poly,pcbnew.F_Cu,0,100,pcbnew.ERROR_OUTSIDE);output['pads'].append({'number':p.GetNumber(),'net':p.GetNetname(),'polygons':contours(poly),'paste_margin':list(p.GetSolderPasteMargin(pcbnew.F_Cu))})
for t in b.GetTracks():
 if t.GetLayer()!=pcbnew.F_Cu:continue
 if abs(t.GetPosition().x-fp.GetPosition().x)>3e6 or abs(t.GetPosition().y-fp.GetPosition().y)>3e6:continue
 poly=pcbnew.SHAPE_POLY_SET();t.TransformShapeToPolygon(poly,pcbnew.F_Cu,0,100,pcbnew.ERROR_OUTSIDE);output['tracks'].append({'uuid':t.m_Uuid.AsString(),'net':t.GetNetname(),'polygons':contours(poly)})
for z in b.Zones():
 if not z.GetIsRuleArea() and z.IsOnLayer(pcbnew.F_Cu):output['zones'].extend(contours(z.GetFilledPolysList(pcbnew.F_Cu)))
(ROOT/'analysis/v1_1_release_20261012/identities/u7-native.json').write_text(json.dumps(output,indent=2))
