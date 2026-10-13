#!/usr/bin/env python3
"""Read-only exact authored-delta and model registration review of integrated PCB."""
from pathlib import Path
import sys,json,hashlib,copy,re
from decimal import Decimal
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));import build_metadata as m
a=m.a;P=Path.home()/'Repositories/ai-working/scratch/stratolink-release-20261012';B=P/'integrated-u7-r2';F=P/'release-candidate';A=P/'power/balancer-reviewed';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
b,f,auth=[a.parse((p/'stratolink.kicad_pcb').read_text()) for p in [B,F,A]]
manifest=json.loads((HERE.parent/'power/balancer-final-candidate.json').read_text())
def norm(n):
 if not isinstance(n,list):
  if n=='Net-(U1-VBAT)':return '/VBAT'
  if isinstance(n,str) and re.fullmatch(r'-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?',n):return str(Decimal(n).normalize())
  return n
 return [norm(v) for v in n]
def objects(t,kinds):return {a.scalar(n,'uuid'):n for n in t if isinstance(n,list) and n[0] in kinds}
old,new,author=[objects(t,{'segment','via'}) for t in [b,f,auth]]
removed={d['uuid'] for d in manifest['removed_objects']};added={d['uuid'] for d in manifest['added_objects']}
assert old.keys()-new.keys()==removed,('removed',old.keys()-new.keys(),removed)
assert new.keys()-old.keys()==added,('added',new.keys()-old.keys(),added)
for uid in old.keys()&new.keys():assert norm(old[uid])==norm(new[uid]),('changed existing conductor',uid)
for uid in added:assert norm(new[uid])==norm(author[uid]),('changed authored conductor',uid)
strip=lambda n,keys:[c for c in n if not(isinstance(c,list) and c and c[0] in keys)]
zz0,zz1=[objects(t,{'zone'}) for t in [b,f]];assert zz0.keys()==zz1.keys()
for uid in zz0:assert norm(strip(zz0[uid],{'filled_polygon','filled_areas_thickness'}))==norm(strip(zz1[uid],{'filled_polygon','filled_areas_thickness'})),('zone',uid)
gg0,gg1=[objects(t,{'gr_line','gr_rect','gr_arc','gr_poly','gr_curve','gr_circle','gr_text','gr_text_box'}) for t in [b,f]];assert gg0==gg1,'board drawing/outline change'
fps=lambda t:{a.prop(n,'Reference'):n for n in a.nodes(t,'footprint')}
basefps,finalfps,authorfps=map(fps,[b,f,auth]);assert set(finalfps)-set(basefps)=={'U8','R24','R25','R26','C22'}
for ref in ['U8','R24','R25','R26','C22']:
 assert norm([strip(p,{'pinfunction','pintype'}) for p in a.nodes(authorfps[ref],'pad')])==norm([strip(p,{'pinfunction','pintype'}) for p in a.nodes(finalfps[ref],'pad')]),('new pad altered',ref)
# Models are unchanged by the integration, including component position and flip.
registrations={}
for ref in finalfps:
 x,y=authorfps[ref],finalfps[ref]
 for key in ['at','layer','model']:
  assert norm(a.nodes(x,key))==norm(a.nodes(y,key)),('model registration',ref,key)
 registrations[ref]=dict(at=a.one(y,'at'),layer=a.scalar(y,'layer'),model_count=len(a.nodes(y,'model')))
result={'status':'PASS','pcb_sha256':sha(F/'stratolink.kicad_pcb'),'schematic_sha256':sha(F/'stratolink.kicad_sch'),'baseline_pcb_sha256':sha(B/'stratolink.kicad_pcb'),'author_pcb_sha256':sha(A/'stratolink.kicad_pcb'),'retained_conductor_count':len(old.keys()&new.keys()),'retained_conductors_exact_except_VBAT_rename':True,'removed_conductors_exact_author_scope':len(removed),'added_conductors_exact_author_scope':len(added),'zone_outlines_and_parameters_exact':len(zz0),'board_artwork_and_edge_geometry_exact':len(gg0),'new_13_pad_nodes_exact_author_geometry_and_nets':True,'footprint_count':len(finalfps),'all_component_and_model_registrations_equal_frozen_reviewed_source':True,'registrations':registrations}
(HERE/'balance-integrated-geometry-review.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='registrations'},indent=2))
