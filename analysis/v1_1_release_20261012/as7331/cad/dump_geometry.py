import sys,json,pcbnew,wx
app=wx.App(False);b=pcbnew.LoadBoard(sys.argv[1]);o={'pads':[],'tracks':[],'lines':[]}
def pt(p):return [pcbnew.ToMM(p.x),pcbnew.ToMM(p.y)]
for f in b.GetFootprints():
 for p in f.Pads():o['pads'].append(dict(ref=f.GetReference(),n=p.GetNumber(),at=pt(p.GetPosition()),size=pt(p.GetSize()),angle=p.GetOrientationDegrees(),net=p.GetNetname(),side=f.GetLayerName(),pth=p.GetAttribute()==pcbnew.PAD_ATTRIB_PTH))
 for g in f.GraphicalItems():
  if hasattr(g,'GetStart') and g.GetLayerName() in ['F.Fab','B.Fab']:o['lines'].append(dict(ref=f.GetReference(),s=pt(g.GetStart()),e=pt(g.GetEnd()),side=g.GetLayerName()))
for t in b.GetTracks():o['tracks'].append(dict(uuid=t.m_Uuid.AsString(),s=pt(t.GetStart()),e=pt(t.GetEnd()),net=t.GetNetname(),side=t.GetLayerName(),width=pcbnew.ToMM(t.GetWidth(t.GetLayer()) if t.GetClass()=='PCB_VIA' else t.GetWidth()),via=t.GetClass()=='PCB_VIA'))
open(sys.argv[2],'w').write(json.dumps(o))
