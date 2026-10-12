#!/usr/bin/env python3
"""Independent read-only suspension pad/profile/drill/mask/paste audit."""
from pathlib import Path
import hashlib,json,re,subprocess
import pcbnew,wx
H=Path(__file__).resolve().parent;ROOT=H.parents[3]
P=Path.home()/'Repositories/ai-working/scratch/stratolink-suspension-pth/candidate/stratolink.kicad_pcb'
EXPECTED='82926d9dfc728dca41c9d0970c69a5144fb9079380a298337381c199698f80f4'
source=P.read_bytes();assert hashlib.sha256(source).hexdigest()==EXPECTED
app=wx.App(False);b=pcbnew.LoadBoard(str(P));c=b.GetConnectivity();poly=pcbnew.SHAPE_POLY_SET();assert b.GetBoardPolygonOutlines(poly,False,None,False,False);assert poly.OutlineCount()==1 and poly.HoleCount(0)==0
centers={'H1':(55.665,31.745),'H2':(74.327,31.745)};mounts=[]
for f in b.GetFootprints():
 if f.GetReference() not in centers:continue
 pads=list(f.Pads());assert len(pads)==1;p=pads[0];x,y=centers[f.GetReference()]
 assert p.GetPosition()==pcbnew.VECTOR2I(pcbnew.FromMM(x),pcbnew.FromMM(y))
 assert p.GetNumber()=='1' and p.GetNetname()=='GND' and p.GetAttribute()==pcbnew.PAD_ATTRIB_PTH
 assert p.GetDrillSize()==pcbnew.VECTOR2I(2000000,2000000) and p.GetSize()==pcbnew.VECTOR2I(3200000,3200000)
 assert p.IsOnLayer(pcbnew.F_Cu) and p.IsOnLayer(pcbnew.B_Cu) and p.IsOnLayer(pcbnew.F_Mask) and p.IsOnLayer(pcbnew.B_Mask)
 assert not p.IsOnLayer(pcbnew.F_Paste) and not p.IsOnLayer(pcbnew.B_Paste)
 assert p.GetSolderMaskExpansion(pcbnew.F_Mask)==p.GetSolderMaskExpansion(pcbnew.B_Mask)==0
 assert poly.Contains(p.GetPosition()),'Old routed circle still excludes drilled location from profile'
 nodes={(x.GetParentFootprint().GetReference(),x.GetNumber()) for x in c.GetConnectedItems(p) if isinstance(x,pcbnew.PAD)}|{(f.GetReference(),'1')}
 original={k for k in nodes if k[0] not in centers};assert len(original)==67 and len(nodes)==69
 mounts.append(dict(ref=f.GetReference(),at_mm=[x,y],drill_mm=2.0,copper_OD_mm=3.2,nominal_annulus_mm=.6,front_back_mask_OD_mm=3.2,original_ground_nodes=len(original),all_ground_nodes=len(nodes)))
assert len(mounts)==2 and c.GetUnconnectedCount(False)==0

def drills(path):
 text=path.read_text();tools={};tool=None;hits=[]
 for l in text.splitlines():
  m=re.fullmatch(r'T(\d+)C([\d.]+)',l)
  if m:tools[int(m[1])]=float(m[2]);continue
  m=re.fullmatch(r'T(\d+)',l)
  if m:tool=int(m[1]);continue
  m=re.fullmatch(r'X(-?[\d.]+)Y(-?[\d.]+)',l)
  if m:hits.append(dict(x=float(m[1]),y=-float(m[2]),diameter=tools[tool]))
 return text,hits
pt,ph=drills(H/'stratolink-PTH.drl');nt,nh=drills(H/'stratolink-NPTH.drl')
assert 'Plated' in pt and 'NonPlated' in nt;assert 'G85' not in pt+nt
for ref,(x,y) in centers.items():
 hit=[h for h in ph if abs(h['x']-x)<.00051 and abs(h['y']-y)<.00051];assert len(hit)==1 and hit[0]['diameter']==2.0,(ref,hit)
 assert not any(abs(h['x']-x)<.00051 and abs(h['y']-y)<.00051 for h in nh)
assert len(ph)==167 and len(nh)==3
assert sorted((h['x'],h['y'],h['diameter']) for h in nh)==[(57.764,83.688,.991),(62.844,82.672,.991),(62.844,84.704,.991)]
# Check actual native Gerber flashes, not just input pad settings.
plots={}
for name in ['F_Cu.gtl','B_Cu.gbl','F_Mask.gts','B_Mask.gbs','F_Paste.gtp','B_Paste.gbp']:
 path=H/('stratolink-'+name);text=path.read_text();apertures={int(i):float(d) for i,d in re.findall(r'%ADD(\d+)C,([\d.]+)\*%',text)}
 ref=None;ap=None;found=[]
 for l in text.splitlines():
  m=re.fullmatch(r'%TO\.(?:C|P),([^,*]+)(?:,[^*]*)?\*%',l)
  if m:ref=m[1]
  if l=='%TD*%':ref=None
  m=re.fullmatch(r'D(\d+)\*',l)
  if m:ap=int(m[1])
  if 'D03*' in l and ref in centers:found.append(dict(ref=ref,command=l,diameter=apertures.get(ap)))
 if 'Paste' in name:assert not found
 else:assert len(found)==2 and {p['ref'] for p in found}==set(centers) and all(p['diameter']==3.2 for p in found),(name,found)
 plots[name]=found
edge=(H/'stratolink-Edge_Cuts.gm1').read_text();assert '%TF.FileFunction,Profile,NP*%' in edge
assert P.read_bytes()==source
result=dict(status='pass',candidate_sha256=EXPECTED,kicad=pcbnew.GetBuildVersion(),candidate_unchanged=True,mounts=mounts,PTH_hit_count=len(ph),NPTH_hit_count=len(nh),remaining_NPTH_hits=nh,plated_top_holes_present=True,old_top_routed_cutouts_absent=True,outline_count=1,internal_routed_holes=0,mask_copper_and_paste_flashes=plots,no_excellon_slots=True,native_opens=0,export_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in H.iterdir() if p.suffix in ['.gtl','.gbl','.gts','.gbs','.gtp','.gbp','.gm1','.drl']})
(H/'independent-review.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
