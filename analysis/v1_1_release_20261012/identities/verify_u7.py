#!/usr/bin/env python3
"""Native scope/connectivity and copper evidence on frozen copies, not canonical CAD."""
from pathlib import Path
import sys,json,copy,hashlib
import pcbnew,wx
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));import build_metadata as m;import build_u7 as u
a=m.a;ROOT=m.ROOT;OUT=u.OUT;BASE=m.OUT
sys.path.insert(0,str(ROOT/'analysis/v1_1_solar_attachments_20261012/materials'));from extract_native import contours
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def strip(n,k):return [x for x in n if not(isinstance(x,list) and x and x[0] in k)]
x,y=[a.parse((p/'stratolink.kicad_pcb').read_text()) for p in [BASE,OUT]]
assert strip(x,{'footprint','segment','via','zone'})==strip(y,{'footprint','segment','via','zone'})
for of,nf in zip(a.nodes(x,'footprint'),a.nodes(y,'footprint')):
 ref=a.prop(of,'Reference');assert ref==a.prop(nf,'Reference')
 if ref!='U7':assert of==nf,ref;continue
 aa,bb=copy.deepcopy(of),copy.deepcopy(nf)
 for op,np in zip(a.nodes(aa,'pad'),a.nodes(bb,'pad')):
  assert a.scalar(op,'uuid')==a.scalar(np,'uuid')
  if op[1] in {'3','6'}:assert strip(op,{'zone_connect'})==strip(np,{'zone_connect'});op[:]=strip(op,{'zone_connect'});np[:]=strip(np,{'zone_connect'})
  else:assert op==np
 assert strip(aa,{'solder_paste_margin_ratio'})==strip(bb,{'solder_paste_margin_ratio'})
 assert a.scalar(bb,'solder_paste_margin_ratio')=='-0.05'
objects=lambda t,kind:{a.scalar(n,'uuid'):n for n in a.nodes(t,kind)}
old,new=[objects(t,'segment') for t in [x,y]];assert old.keys()-new.keys()==u.REMOVE
for uid in old.keys()&new.keys():assert old[uid]==new[uid]
added_tracks=sorted(new.keys()-old.keys())
old,new=[objects(t,'via') for t in [x,y]];assert old.keys()<=new.keys()
for uid in old:assert old[uid]==new[uid]
added_vias=sorted(new.keys()-old.keys());assert len(added_vias)==2
old,new=[objects(t,'zone') for t in [x,y]];assert old.keys()<=new.keys()
for uid in old:assert strip(old[uid],{'filled_polygon','filled_areas_thickness'})==strip(new[uid],{'filled_polygon','filled_areas_thickness'})
assert len(new.keys()-old.keys())==2
for n in ['stratolink.kicad_sch','stratolink.kicad_pro','fp-lib-table','sym-lib-table']:assert (BASE/n).read_bytes()==(OUT/n).read_bytes(),n
app=wx.App(False);ob,nb=[pcbnew.LoadBoard(str(p/'stratolink.kicad_pcb')) for p in [BASE,OUT]]
for b in [ob,nb]:pcbnew.ZONE_FILLER(b).Fill(b.Zones());b.BuildConnectivity()
pads=lambda b:{p.m_Uuid.AsString():p for f in b.GetFootprints() for p in f.Pads()}
pp=[pads(b) for b in [ob,nb]];assert pp[0].keys()==pp[1].keys()
reach=lambda b,p:{p.m_Uuid.AsString()}|{q.m_Uuid.AsString() for q in b.GetConnectivity().GetConnectedItems(p) if isinstance(q,pcbnew.PAD)}
for uid in pp[0]:
 p0,p1=[p[uid] for p in pp];assert p0.GetNetname()==p1.GetNetname();assert reach(ob,p0)==reach(nb,p1),uid
assert nb.GetConnectivity().GetUnconnectedCount(False)==0
# New library equals placed pad settings and native library checker agrees.
f=next(f for f in nb.GetFootprints() if f.GetReference()=='U7');lib=pcbnew.FootprintLoad(str(OUT/'lib'),str(f.GetFPID().GetLibItemName()));assert not f.FootprintNeedsUpdate(lib,1)
for p,q in zip(sorted(f.Pads(),key=lambda p:p.GetNumber()),sorted(lib.Pads(),key=lambda p:p.GetNumber())):
 assert p.GetLocalZoneConnection()==q.GetLocalZoneConnection();assert p.GetSolderPasteMargin(pcbnew.F_Cu)==q.GetSolderPasteMargin(pcbnew.F_Cu)
geometry={}
for label,b in [('before',ob),('after',nb)]:
 out={'pads':[],'tracks':[],'zones':{},'copper':{}}
 for f in b.GetFootprints():
  if f.GetReference() not in {'U7','U6','C6','C19','C20','R8'}:continue
  for p in f.Pads():
   layer=pcbnew.B_Cu if f.IsFlipped() else pcbnew.F_Cu;poly=pcbnew.SHAPE_POLY_SET();p.TransformShapeToPolygon(poly,layer,0,100,pcbnew.ERROR_OUTSIDE);out['pads'].append(dict(ref=f.GetReference(),pad=p.GetNumber(),uuid=p.m_Uuid.AsString(),net=p.GetNetname(),layer=b.GetLayerName(layer),polygons=contours(poly)))
 for t in b.GetTracks():
  if abs(t.GetPosition().x/1e6-70.5)>6 or abs(t.GetPosition().y/1e6-38)>5:continue
  for layer in [pcbnew.F_Cu,pcbnew.B_Cu]:
   if not t.IsOnLayer(layer):continue
   poly=pcbnew.SHAPE_POLY_SET();t.TransformShapeToPolygon(poly,layer,0,100,pcbnew.ERROR_OUTSIDE);out['tracks'].append(dict(uuid=t.m_Uuid.AsString(),net=t.GetNetname(),layer=b.GetLayerName(layer),via=isinstance(t,pcbnew.PCB_VIA),polygons=contours(poly)))
 for layer in [pcbnew.F_Cu,pcbnew.B_Cu]:
  zpoly=[]
  for z in b.Zones():
   if not z.GetIsRuleArea() and z.IsOnLayer(layer):zpoly.extend(contours(z.GetFilledPolysList(layer)))
  out['zones'][b.GetLayerName(layer)]=zpoly
  poly=pcbnew.SHAPE_POLY_SET();b.ConvertBrdLayerToPolygonalContours(layer,poly);poly.Simplify();out['copper'][b.GetLayerName(layer)]=contours(poly)
 geometry[label]=out
(HERE/'u7-geometry-native.json').write_text(json.dumps(geometry,separators=(',',':'))+'\n')
res=dict(status='PASS',baseline_sha256=sha(BASE/'stratolink.kicad_pcb'),candidate=str(OUT),pcb_sha256=sha(OUT/'stratolink.kicad_pcb'),schematic_sha256=sha(OUT/'stratolink.kicad_sch'),u7_library_sha256=sha(OUT/'lib'/('Stratolink_v1p1_U7_PQFN50P200X200100-12N.kicad_mod')),physical_pads=len(pp[0]),physical_pad_islands_identical=True,unconnected=0,only_U7_pad_overrides_and_paste_changed=True,removed_tracks=sorted(u.REMOVE),added_tracks=added_tracks,added_vias=added_vias,added_keepouts=sorted(new.keys()-old.keys()),all_other_source_objects_exact=True)
(HERE/'u7-verification.json').write_text(json.dumps(res,indent=2)+'\n');print(json.dumps(res,indent=2))
