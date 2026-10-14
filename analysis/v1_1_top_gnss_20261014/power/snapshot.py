from pathlib import Path
import sys,json,hashlib,pcbnew,wx
def contours(poly):
 def chain(c):return [[c.CPoint(i).x/1e6,c.CPoint(i).y/1e6] for i in range(c.PointCount())]
 return [{'shell':chain(poly.Outline(i)),'holes':[chain(poly.Hole(i,k)) for k in range(poly.HoleCount(i))]} for i in range(poly.OutlineCount())]
p=Path(sys.argv[1]);out=Path(sys.argv[2]);raw=p.read_bytes();app=wx.App(False);b=pcbnew.LoadBoard(str(p));d=dict(source=str(p),sha256=hashlib.sha256(raw).hexdigest(),footprints={},pads=[],tracks=[],zones=[],graphics=[]);xy=lambda q:[q.x/1e6,q.y/1e6]
for f in b.GetFootprints():
 ref=f.GetReference();d['footprints'][ref]=dict(at=xy(f.GetPosition()),angle=f.GetOrientationDegrees(),layer=f.GetLayerName(),fp=str(f.GetFPID().GetLibItemName()),value=f.GetValue(),fields={q.GetName():q.GetText() for q in f.GetFields()},courtyard=[],fab=[])
 for g in f.GraphicalItems():
  if isinstance(g,pcbnew.PCB_SHAPE) and g.GetLayer() in [pcbnew.F_Fab,pcbnew.B_Fab,pcbnew.F_CrtYd,pcbnew.B_CrtYd]:
   d['footprints'][ref]['courtyard' if g.GetLayer()in[pcbnew.F_CrtYd,pcbnew.B_CrtYd]else'fab'].append(dict(uuid=g.m_Uuid.AsString(),start=xy(g.GetStart()),end=xy(g.GetEnd()),width=g.GetWidth()/1e6,shape=g.GetShape()))
 for q in f.Pads():
  poly=pcbnew.SHAPE_POLY_SET();layer=pcbnew.B_Cu if q.IsOnLayer(pcbnew.B_Cu)else pcbnew.F_Cu;q.TransformShapeToPolygon(poly,layer,0,1000,pcbnew.ERROR_OUTSIDE);d['pads'].append(dict(ref=ref,pin=q.GetNumber(),uuid=q.m_Uuid.AsString(),at=xy(q.GetPosition()),net=q.GetNetname(),layers=[b.GetLayerName(l)for l in[pcbnew.F_Cu,pcbnew.B_Cu]if q.IsOnLayer(l)],size=xy(q.GetSize()),polygons=contours(poly)))
for t in b.GetTracks():
 row=dict(uuid=t.m_Uuid.AsString(),kind=t.GetClass(),net=t.GetNetname(),layer=t.GetLayerName(),start=xy(t.GetStart()),end=xy(t.GetEnd()),width=(t.GetWidth(pcbnew.F_Cu) if isinstance(t,pcbnew.PCB_VIA)else t.GetWidth())/1e6,length=t.GetLength()/1e6)
 if isinstance(t,pcbnew.PCB_ARC):row['mid']=xy(t.GetMid())
 if isinstance(t,pcbnew.PCB_VIA):row['drill']=t.GetDrill()/1e6
 d['tracks'].append(row)
for z in b.Zones():
 if z.GetNetname()not in['+SOLAR','GND']:continue
 for l in[pcbnew.F_Cu,pcbnew.B_Cu]:
  if z.IsOnLayer(l):d['zones'].append(dict(uuid=z.m_Uuid.AsString(),net=z.GetNetname(),layer=b.GetLayerName(l),polygons=contours(z.GetFilledPolysList(l))))
for g in b.GetDrawings():
 if isinstance(g,pcbnew.PCB_SHAPE)and g.IsOnCopperLayer():
  poly=pcbnew.SHAPE_POLY_SET();g.TransformShapeToPolygon(poly,g.GetLayer(),0,1000,pcbnew.ERROR_OUTSIDE);d['graphics'].append(dict(uuid=g.m_Uuid.AsString(),net=g.GetNetname(),layer=g.GetLayerName(),polygons=contours(poly)))
out.write_text(json.dumps(d,indent=2)+'\n');assert p.read_bytes()==raw
print('Saved',out,d['sha256'])
