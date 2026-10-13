#!/usr/bin/env python3
"""Check the merger's power delta independently against the authored freeze."""
from pathlib import Path
import importlib.util, json, hashlib, re
from decimal import Decimal
HERE=Path(__file__).resolve().parent
sp=importlib.util.spec_from_file_location('build',HERE/'build_balancer_candidate.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
S=m.OUT.parent.parent;F=S/'release-candidate';B=S/'integrated-u7-r2';A=m.OUT.parent/'balancer-reviewed'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
protected={n:sha(F/n) for n in ['stratolink.kicad_pcb','stratolink.kicad_sch','stratolink.kicad_pro','stratolink.kicad_dru']}
assert protected['stratolink.kicad_pcb']=='490af47db22ef076938c17319782f194623d8f8b6a3f864a2e0cc23b3d025b15'
assert protected['stratolink.kicad_sch']=='044984037a7346adc92ee9ea142e6c285ee7f6b66efc87e0a1ad195495379cc9'
def normal(n):
 if not isinstance(n,list):return n
 # Native save canonicalizes e.g. 63.0 to 63; allow only numeric geometry fields.
 numeric={'at','start','end','width','size','drill','xyz','xy','offset','rotate','scale','thermal_gap','thermal_bridge_width'}
 return [Decimal(x) if i and n[0] in numeric and isinstance(x,str) and re.fullmatch(r'-?\d+(\.\d+)?',x) else normal(x) for i,x in enumerate(n)]
parse=lambda p:normal(m.a.parse(p.read_text().replace('"Net-(U1-VBAT)"','"/VBAT"')))
b,a,f=[parse(x/'stratolink.kicad_pcb') for x in [B,A,F]]
manifest=json.loads((HERE/'balancer-final-candidate.json').read_text())
tracks=lambda board:{m.a.scalar(x,'uuid'):x for x in board[1:] if isinstance(x,list) and x[0] in ['segment','via']}
bt,at,ft=map(tracks,[b,a,f]);deleted={x['uuid'] for x in manifest['removed_objects']};added={x['uuid'] for x in manifest['added_objects']}
assert bt.keys()-ft.keys()==deleted and ft.keys()-bt.keys()==added
assert all(bt[k]==ft[k] for k in bt.keys()&ft.keys())
assert all(at[k]==ft[k] for k in added)
fps=lambda board:{m.a.prop(x,'Reference'):x for x in m.a.nodes(board,'footprint')}
bf,af,ff=map(fps,[b,a,f]);assert ff.keys()-bf.keys()==set(m.NEW)
def physical(fp,allow_mid=False,allow_thermal=False):
 result=[]
 for x in fp[2:]:
  if not isinstance(x,list) or x[0] in ['property','descr','path','attr','embedded_fonts']:continue
  if x[0]=='pad':
   ignore={'pinfunction','pintype'}
   if allow_mid and x[1]=='3':ignore.add('net')
   if allow_thermal and x[1]=='1':ignore|={'thermal_gap','thermal_bridge_width'}
   x=[q for q in x if not isinstance(q,list) or q[0] not in ignore]
  result.append(x)
 return result
for ref in bf:assert physical(bf[ref],ref=='C5',ref in ['D3','J4'])==physical(ff[ref],ref=='C5',ref in ['D3','J4']),('Old physical geometry changed',ref)
for ref in m.NEW:assert physical(af[ref])==physical(ff[ref]),('New physical geometry changed',ref)
thermal=json.loads((HERE/'thermal-author-manifest.json').read_text())
for row in thermal['changes']:
 p=next(x for x in m.a.nodes(ff[row['reference']],'pad') if m.a.scalar(x,'uuid')==row['pad_uuid'])
 assert all(float(m.a.scalar(p,k))==v for k,v in row['after'].items())
sch=parse(F/'stratolink.kicad_sch');symbols={m.a.prop(x,'Reference'):x for x in m.a.nodes(sch,'symbol')}
for ref in ['R1']+list(m.NEW):
 for field in ['Value','Supplier Part','Manufacturer_Part_Number']:
  assert m.a.prop(ff[ref],field)==m.a.prop(symbols[ref],field)==m.a.prop(af[ref],field),(ref,field)
for x in [ff['R1'],symbols['R1']]:
 assert m.a.prop(x,'Manufacturer')=='FOJAN'
 assert '7.50' in m.a.prop(x,'Description') and '8.25' not in m.a.prop(x,'Description')
 assert m.a.prop(x,'Datasheet')=='https://www.lcsc.com/product-detail/C3013187.html'
for x in [ff['C5'],symbols['C5']]:assert 'connects to SC_MID' in m.a.prop(x,'Assembly_Note')
bp=json.loads((B/'stratolink.kicad_pro').read_text());fp=json.loads((F/'stratolink.kicad_pro').read_text())
erc_exclusions=fp['erc']['erc_exclusions'];assert bp['erc']['erc_exclusions']==[]
assert len(erc_exclusions)==3
assert all(name in row[1] and uid in row[0] and row[0].startswith('pin_to_pin|') for row,name,uid in zip(erc_exclusions,['LTR-390UV INT','TMP117 ALERT','LIS2DH12 SDO/SA0'],['97fe1358-9111-4cae-ace0-69f4a04c9922','d24f236f-77e7-440c-9378-f49a6d546306','82711c1e-7163-4ccd-9fb6-5a60e20408e1']))
fp['erc']['erc_exclusions']=[];assert fp==bp, 'Project change outside independently reviewed ERC exclusion'
assert sha(B/'stratolink.kicad_dru')==protected['stratolink.kicad_dru']
def other(board):
 result=[]
 for x in board[1:]:
  if not isinstance(x,list) or x[0] in ['footprint','segment','via']:continue
  if x[0]=='zone':x=[q for q in x if not isinstance(q,list) or q[0] not in ['filled_polygon','filled_areas_thickness']]
  result.append(x)
 return result
assert other(b)==other(f)
native=json.loads((m.OUT.parent/'integrated-author-check/review.json').read_text());assert native['status']=='PASS' and native['candidate_sha256']['stratolink.kicad_pcb']==protected['stratolink.kicad_pcb']
drcpath=HERE.parent/'final-drc.json';drc=json.loads(drcpath.read_text());assert len(drc['violations'])==4 and all(x['type']=='silk_over_copper' for x in drc['violations']) and not drc['unconnected_items'] and not drc.get('schematic_parity',[])
assert protected=={n:sha(F/n) for n in protected}
report=dict(status='PASS',candidate=str(F),candidate_sha256=protected,authored_pcb_sha256=sha(A/'stratolink.kicad_pcb'),native_check=native,scope=dict(removed_original_routes=len(deleted),added_routes=len(added),all_surviving_preintegrated_routes_semantically_exact=True,all_authored_new_routes_semantically_exact=True,allowed_numeric_canonicalization='Native save 63.0→63 allowed only in numeric geometry fields',all_existing_component_physical_geometry_preserved=True,all_new_component_geometry_models_positions_preserved=True,only_declared_existing_pad_thermals_applied=True,all_other_board_objects_semantically_exact=True,project_unchanged_except_reviewed_ERC_exclusion=erc_exclusions,custom_rules_unchanged=True,supplier_fields_and_R1_C5_metadata_correct=True),enabled_drc_report_sha256=sha(drcpath),enabled_drc=dict(silk_warnings=4,opens=0,parity=0,other_violations=0),qualification_limit='CAD integration verified; cold/startup/load/solar-input and physical assembly qualification remain measurements, as specified in the power audit and pilot acceptance plan.')
(HERE/'integrated-power-review.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
