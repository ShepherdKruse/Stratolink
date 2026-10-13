#!/usr/bin/env python3
"""Freeze authored source and enumerate its strict delta; run with KiCad Python."""
from pathlib import Path
import importlib.util, json, hashlib, subprocess, shutil
HERE=Path(__file__).resolve().parent
sp=importlib.util.spec_from_file_location('build',HERE/'build_balancer_candidate.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
OUT=m.OUT.parent/'balancer-reviewed'
assert not OUT.exists(), 'Never overwrite a reviewed source'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
names=['stratolink.kicad_pcb','stratolink.kicad_sch','stratolink.kicad_pro','fp-lib-table','sym-lib-table']
libs=subprocess.check_output(['git','ls-tree','-r','--name-only',m.BASE+':hardware/pcb/lib'],cwd=m.ROOT,text=True).splitlines()
names+=['lib/'+n for n in libs]+['lib/Stratolink_Power.kicad_sym']
for n in names:
 p=OUT/n;p.parent.mkdir(parents=True,exist_ok=True);assert not (m.OUT/n).is_symlink();shutil.copyfile(m.OUT/n,p)
def ast(text):return m.a.parse(text.replace('"Net-(U1-VBAT)"','"/VBAT"'))
old=ast(subprocess.check_output(['git','show',m.BASE+':hardware/pcb/stratolink.kicad_pcb'],cwd=m.ROOT,text=True));new=ast((OUT/'stratolink.kicad_pcb').read_text())
items=lambda b:{m.a.scalar(n,'uuid'):n for n in b[1:] if isinstance(n,list) and n[0] in ['segment','via']}
ot,nt=items(old),items(new)
removed=sorted(ot.keys()-nt.keys());added=sorted(nt.keys()-ot.keys())
assert set(removed)==set(json.loads((HERE/'adc-stub-removal.json').read_text())['removed_uuids'])|{'6cb4b0b4-5fa9-462d-95d3-a28344e6cc28'}
assert all(ot[k]==nt[k] for k in ot.keys()&nt.keys()),'Surviving track changed'
fps=lambda b:{m.a.prop(f,'Reference'):f for f in m.a.nodes(b,'footprint')}
of,nf=fps(old),fps(new);assert nf.keys()-of.keys()==set(m.NEW)
changed=sorted(k for k in of if of[k]!=nf[k]);assert changed==['C5','D3','J4','R1'],changed
padchanges=[]
for ref in of:
 before={m.a.scalar(p,'uuid'):p for p in m.a.nodes(of[ref],'pad')};after={m.a.scalar(p,'uuid'):p for p in m.a.nodes(nf[ref],'pad')};assert before.keys()==after.keys()
 for uid in before:
  op,np=before[uid],after[uid]
  if op==np:continue
  fields=['thermal_gap','thermal_bridge_width'] if ref in ['D3','J4'] else ['net','pinfunction','pintype']
  assert (ref,op[1]) in [('D3','1'),('J4','1'),('C5','3')]
  clean=lambda p:[q for q in p if not isinstance(q,list) or q[0] not in fields]
  assert clean(op)==clean(np),('Unexpected original pad change',ref,uid)
  padchanges.append(dict(reference=ref,pad=op[1],pad_uuid=uid,fields=fields))
# Every unrelated top-level object is identical after removal of fill caches and
# the deliberate net-label rename. Footprints/tracks are compared separately.
def other(b):
 result=[]
 for n in b[1:]:
  if not isinstance(n,list) or n[0] in ['footprint','segment','via']:continue
  if n[0]=='zone':n=[x for x in n if not isinstance(x,list) or x[0] not in ['filled_polygon','filled_areas_thickness']]
  result.append(n)
 return result
assert other(old)==other(new),'Unrelated board geometry or metadata changed'
for ref in ['R1']+list(m.NEW):
 s=m.a.parse((OUT/'stratolink.kicad_sch').read_text());sym=next(n for n in m.a.nodes(s,'symbol') if m.a.prop(n,'Reference')==ref)
 for key in ['Supplier Part','Manufacturer_Part_Number']:
  assert m.a.prop(sym,key)==m.a.prop(nf[ref],key),(ref,key)
thermal=dict(pcb_sha256=sha(OUT/'stratolink.kicad_pcb'),changes=[])
for ref in ['D3','J4']:
 p=next(p for p in m.a.nodes(nf[ref],'pad') if p[1]=='1')
 assert m.a.one(p,'thermal_gap')==['0.25'] and m.a.one(p,'thermal_bridge_width')==['0.25']
 thermal['changes'].append(dict(reference=ref,pad='1',pad_uuid=m.a.scalar(p,'uuid'),before=dict(thermal_gap=None,thermal_bridge_width=None),after=dict(thermal_gap=.25,thermal_bridge_width=.25)))
(HERE/'thermal-author-manifest.json').write_text(json.dumps(thermal,indent=2)+'\n')
route_rows=json.loads((m.OUT.parent/'routes.json').read_text())
summary=[]
for row in route_rows:
 length=sum(((q['start'][0]-q['end'][0])**2+(q['start'][1]-q['end'][1])**2)**.5 for q in row['segments'])
 summary.append(dict(net=row['net'],first=row['first'],second=row['second'],length_mm=length,vias=len(row['vias']),width_mm=row['width'],copper_resistance_20C_ohm_excluding_vias=1.72e-8*length*1e-3/(row['width']*1e-3*35e-6)))
report=dict(status='routed-authored-candidate-frozen-pending-independent-and-integrated-release-checks',baseline=m.BASE,path=str(OUT),files={n:sha(OUT/n) for n in names},removed_objects=[dict(uuid=k,kind=ot[k][0],net=m.a.scalar(ot[k],'net')) for k in removed],added_objects=[dict(uuid=k,kind=nt[k][0],net=m.a.scalar(nt[k],'net')) for k in added],existing_changed_footprints=changed,existing_changed_pads=padchanges,new_parts=m.NEW,route_summary=summary,checks=dict(surviving_tracks_exact=True,unrelated_board_geometry_metadata_exact=True,old_pad_geometry_exact=True,new_part_supplier_metadata_matches_schematic=True),limitations=['Authored candidate uses baseline header geometry; final integrated J4 has elongated land.','D3.1/J4.1 local .25 mm gap and .25 mm bridge widths require matching local-footprint metadata freeze during integration.','Final integrated project DRC and independent physical-pad islands remain release gates.','Native CAD checks do not establish cold capacitor balance, electrochemical leakage, solar input limits, or physical assembly tolerances.'])
(HERE/'balancer-final-candidate.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
print(json.dumps(dict(path=str(OUT),files={k:v for k,v in report['files'].items() if k in names[:5]},removed=len(removed),added=len(added),thermal=thermal),indent=2))
