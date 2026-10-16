"""Read-only copper extraction for native plotted-mask checks."""
from pathlib import Path
import sys,json,hashlib,pcbnew,wx
project=Path(sys.argv[1]).resolve();out=Path(sys.argv[2]).resolve();out.mkdir(parents=True,exist_ok=True);p=project/'stratolink.kicad_pcb';raw=p.read_bytes();app=wx.App(False);b=pcbnew.LoadBoard(str(p));rows=[];targets=[]
def xy(q):return[q.x/1e6,q.y/1e6]
def contours(poly):
 def chain(c):return[xy(c.CPoint(i))for i in range(c.PointCount())]
 return[{'shell':chain(poly.Outline(i)),'holes':[chain(poly.Hole(i,k))for k in range(poly.HoleCount(i))]}for i in range(poly.OutlineCount())]
def item_poly(item,layer):
 poly=pcbnew.SHAPE_POLY_SET();item.TransformShapeToPolygon(poly,layer,0,100,pcbnew.ERROR_OUTSIDE);return contours(poly)
for f in b.GetFootprints():
 for pad in f.Pads():
  for layer in [pcbnew.F_Cu,pcbnew.B_Cu]:
   if not pad.IsOnLayer(layer):continue
   row={'ref':f.GetReference(),'pin':pad.GetNumber(),'net':pad.GetNetname(),'uuid':pad.m_Uuid.AsString(),'face':'F'if layer==pcbnew.F_Cu else'B','at':xy(pad.GetPosition()),'polygons':item_poly(pad,layer)};rows.append(row)
   if f.GetReference()in['U4','L2']or(f.GetReference()=='U1'and pad.GetNumber()!='21'):targets.append(row)
for t in b.GetTracks():
 for layer in [pcbnew.F_Cu,pcbnew.B_Cu]:
  if t.IsOnLayer(layer):rows.append({'ref':t.GetClass(),'net':t.GetNetname(),'uuid':t.m_Uuid.AsString(),'face':'F'if layer==pcbnew.F_Cu else'B','polygons':item_poly(t,layer)})
for z in b.Zones():
 for layer in [pcbnew.F_Cu,pcbnew.B_Cu]:
  if z.IsOnLayer(layer):rows.append({'ref':'zone','net':z.GetNetname(),'uuid':z.m_Uuid.AsString(),'face':'F'if layer==pcbnew.F_Cu else'B','polygons':contours(z.GetFilledPolysList(layer))})
for g in b.GetDrawings():
 if isinstance(g,pcbnew.PCB_SHAPE)and g.GetLayer()in[pcbnew.F_Cu,pcbnew.B_Cu]:rows.append({'ref':'graphic','net':g.GetNetname(),'uuid':g.m_Uuid.AsString(),'face':'F'if g.GetLayer()==pcbnew.F_Cu else'B','polygons':item_poly(g,g.GetLayer())})
assert len(targets)==30
(out/'native-copper.json').write_text(json.dumps({'pcb_sha256':hashlib.sha256(raw).hexdigest(),'targets':targets,'copper':rows},indent=2)+'\n');assert p.read_bytes()==raw
# Strict reader supports the native Gerber polygon output; unsupported commands fail.
root=next(x for x in [Path.cwd(),*Path(__file__).resolve().parents]if (x/'analysis/v1_1_release_20261012/as7331/finish').is_dir());sys.path.insert(0,str(root/'analysis/v1_1_release_20261012/as7331/finish'));from verify_mask_artwork import parse_mask
for face,ext in [('F','gts'),('B','gbs')]:
 gp=out/('stratolink-'+face+'_Mask.'+ext);regions=parse_mask(gp);(out/(face+'-regions.json')).write_text(json.dumps({'gerber_sha256':hashlib.sha256(gp.read_bytes()).hexdigest(),'regions':regions})+'\n')
