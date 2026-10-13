#!/usr/bin/env python3
"""Structural and native-artwork verification of the cleanup result, read-only."""
from pathlib import Path
import argparse,collections,copy,hashlib,importlib.util,json,re,shutil,subprocess
sp=importlib.util.spec_from_file_location('cleanup',Path(__file__).with_name('clean_erc.py'));c=importlib.util.module_from_spec(sp);sp.loader.exec_module(c);a=c.a

def stripped(obj,key):
 if not isinstance(obj,list):return obj
 return [stripped(x,key) for x in obj if not(isinstance(x,list) and x and x[0]==key)]
def normalize_gerber(p):return '\n'.join(x for x in p.read_text().splitlines() if 'CreationDate' not in x and not x.startswith('G04 Created by'))
def native_comparison_copy(folder, dependencies, target):
 # Refill and serialize copies of BOTH revisions under the identical rules.
 # Generated caches/order are not authored geometry; the complete normalized
 # tree below still checks every pad, trace, outline, zone definition and model.
 target.mkdir(exist_ok=True)
 for name in ('stratolink.kicad_pcb','stratolink.kicad_pro','stratolink.kicad_sch'):
  shutil.copyfile(folder/name,target/name)
 for name in ('stratolink.kicad_dru','fp-lib-table','sym-lib-table'):
  if (dependencies/name).exists():shutil.copyfile(dependencies/name,target/name)
 for name in ('lib','3d'):
  if (dependencies/name).exists() and not (target/name).exists():(target/name).symlink_to(dependencies/name,target_is_directory=True)
 result=subprocess.run([c.CLI,'pcb','drc','--refill-zones','--save-board','--format','json','--output',str(target/'refill-drc.json'),str(target/'stratolink.kicad_pcb')],check=True,capture_output=True,text=True)
 (target/'refill.log').write_text(result.stdout+result.stderr)
 return target
def authored_tree(tree, generated_property_uuids):
 for key in ('pintype','filled_polygon','filled_areas_thickness'):tree=stripped(tree,key)
 for fp in a.nodes(tree,'footprint'):
  ref=a.prop(fp,'Reference')
  for index,field in enumerate(fp):
   if isinstance(field,list) and field and field[0]=='property' and (ref,field[1]) in generated_property_uuids:
    fp[index]=stripped(field,'uuid')
 # Native output can order tracks by the loaded net table. Object order has no
 # geometric meaning; keep each UUID's complete object and all polygon order.
 objects=[x for x in tree if isinstance(x,list) and a.scalar(x,'uuid')]
 identities=[a.scalar(x,'uuid') for x in objects];assert len(identities)==len(set(identities))
 other=[x for x in tree if not(isinstance(x,list) and a.scalar(x,'uuid'))]
 return other+sorted(objects,key=lambda x:a.scalar(x,'uuid'))
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--candidate',type=Path,required=True);args=ap.parse_args();out=args.candidate;audit=out/'erc-audit';base=audit/'before'
 report=json.loads((audit/'report.json').read_text());original=a.parse((base/'stratolink.kicad_sch').read_text());changed=a.parse((out/'stratolink.kicad_sch').read_text())
 for name in ['stratolink.kicad_pcb','stratolink.kicad_sch','stratolink.kicad_pro']:assert c.sha(base/name)==report['source_hashes'][name]
 source_hashes={name:c.sha(out/name) for name in ('stratolink.kicad_pcb','stratolink.kicad_sch','stratolink.kicad_pro','stratolink.kicad_dru')}
 original_board=a.parse((base/'stratolink.kicad_pcb').read_text())
 generated_property_uuids={(a.prop(fp,'Reference'),field[1]) for fp in a.nodes(original_board,'footprint') for field in a.nodes(fp,'property') if not a.one(field,'uuid')}
 comparison_before=native_comparison_copy(base,out,audit/'verification-before')
 comparison_after=native_comparison_copy(out,out,audit/'verification-after')
 bpcb=a.parse((comparison_before/'stratolink.kicad_pcb').read_text());apcb=a.parse((comparison_after/'stratolink.kicad_pcb').read_text());assert authored_tree(bpcb,generated_property_uuids)==authored_tree(apcb,generated_property_uuids),'Authored PCB geometry changed during electrical cleanup/refill'
 fills=lambda tree:{a.scalar(z,'uuid'):a.nodes(z,'filled_polygon') for z in a.nodes(tree,'zone')}
 assert fills(bpcb)==fills(apcb),'Generated copper fill geometry changed'
 oldpro=json.loads((base/'stratolink.kicad_pro').read_text());newpro=json.loads((out/'stratolink.kicad_pro').read_text())
 assert not oldpro['erc'].get('erc_exclusions');newex=newpro['erc']['erc_exclusions'];assert newex==report['erc_marker_exclusions'] and len(newex)==3
 newpro['erc']['erc_exclusions']=oldpro['erc'].get('erc_exclusions',[])
 assert newpro==oldpro,'Only the three named project marker exclusions may change'
 # Exact previous instances except their library IDs; all shapes/wires/text/junctions unchanged.
 oldinst={a.prop(s,'Reference'):s for s in a.nodes(original,'symbol')};newinst={a.prop(s,'Reference'):s for s in a.nodes(changed,'symbol')}
 assert set(newinst)-set(oldinst)=={f['reference'] for f in report['power_flags']}
 for ref,s in oldinst.items():assert stripped(s,'lib_id')==stripped(newinst[ref],'lib_id'),ref
 excluded={'symbol','lib_symbols','no_connect'}
 other=lambda t:[x for x in t if not(isinstance(x,list) and x and x[0] in excluded)]
 assert other(original)==other(changed),'Non-symbol schematic geometry changed'
 oldnc=a.nodes(original,'no_connect');newnc=a.nodes(changed,'no_connect');assert len(newnc)==len(oldnc)+len(report['no_connect_flags']);assert all(n in newnc for n in oldnc)
 oldlibs={x[1]:x for x in a.nodes(a.nodes(original,'lib_symbols')[0],'symbol')};newlibs={x[1]:x for x in a.nodes(a.nodes(changed,'lib_symbols')[0],'symbol')}
 local={x[1]:x for x in a.nodes(a.parse((out/'lib'/(c.LIB+'.kicad_sym')).read_text()),'symbol')}
 for oldid,oldlib in oldlibs.items():
  name=report['library_map'][oldid];newid=c.LIB+':'+name;newlib=copy.deepcopy(newlibs[newid]);embeddedcopy=copy.deepcopy(newlib);embeddedcopy[1]=name
  assert embeddedcopy==local[name],('Embedded/local mismatch',name)
  newlib[1]=oldid;oldbase=oldid.split(':')[-1]
  for child in a.nodes(newlib,'symbol'):child[1]=oldbase+child[1][len(name):]
  before=c.pin_nodes(oldlib);after=c.pin_nodes(newlib);assert before.keys()==after.keys()
  for num,pin in after.items():pin[1]=before[num][1]
  assert newlib==oldlib,('Frozen symbol physical shape/pin label/number changed',oldid)
 before_nets,before_sets,before_types=c.netmap(audit/'before-netlist.xml');after_nets,after_sets,after_types=c.netmap(audit/'after-netlist.xml')
 assert before_nets==after_nets and before_sets==after_sets
 # No disconnect markers on TI pins that are named NC but specified grounded.
 assert after_nets[('U1','9')]=='GND' and after_nets[('U1','17')]=='GND'
 assert all((n['ref'],n['pin']) not in [('U1','9'),('U1','17')] for n in report['no_connect_flags'])
 assert after_types[('U1','18')]=='power_in', 'VBAT is a power terminal, not bidirectional logic'
 assert after_nets[('U1','18')]==after_nets[('C5','1')] and after_nets[('C5','2')]=='GND'
 reservoir_flags=[flag for flag in report['power_flags'] if flag['connection']=='C5.1']
 assert len(reservoir_flags)==1 and reservoir_flags[0]['net']==after_nets[('C5','1')]
 if 'U8' in newinst:
  assert all(after_nets[key]=='/VBAT' for key in [('U8','5'),('C22','1'),('R24','1')])
  assert all(after_nets[key]=='GND' for key in [('U8','2'),('C22','2')])
 artworks={}
 for label,folder in [('before',comparison_before),('after',comparison_after)]:
  target=audit/(label+'-gerbers');target.mkdir(exist_ok=True)
  run=subprocess.run([c.CLI,'pcb','export','gerbers','--layers','F.Cu,B.Cu,F.Mask,B.Mask,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,Edge.Cuts','--output',str(target),str(folder/'stratolink.kicad_pcb')],check=True,capture_output=True,text=True)
  (audit/(label+'-gerbers.log')).write_text(run.stdout+run.stderr);artworks[label]=target
 same=[];copper_serialization=[]
 for p in artworks['before'].iterdir():
  if p.suffix=='.gbrjob':continue
  if normalize_gerber(p)==normalize_gerber(artworks['after']/p.name):same.append(p.name)
  else:
   # Native net numbering can reorder copper draw groups on reload. Copper is
   # proved above by exact UUID-keyed authored objects AND every filled polygon;
   # record these nonidentical exports instead of claiming byte equality.
   assert p.name in ('stratolink-F_Cu.gtl','stratolink-B_Cu.gbl'),('Non-copper artwork changed',p.name)
   copper_serialization.append(dict(file=p.name,before_sha256=c.sha(p),after_sha256=c.sha(artworks['after']/p.name),
     geometry_evidence='Exact normalized authored objects and all native filled polygons match; byte ordering is not asserted equal.'))
 erc=json.loads((audit/'after-erc.json').read_text());filtered=[v for s in erc['sheets'] for v in s['violations']];assert not filtered
 raw=json.loads((audit/'raw-erc.json').read_text());violations=[v for s in raw['sheets'] for v in s['violations']]
 assert len(violations)==3 and collections.Counter(v['severity'] for v in violations)=={'error':2,'warning':1}
 expected={'Symbol U6 Pin 5','Symbol U5 Pin C2','Symbol U7 Pin 3'}
 assert all(v['type']=='pin_to_pin' and any(v['items'][0]['description'].startswith(x) for x in expected) for v in violations),violations
 alls=json.loads((audit/'all-erc.json').read_text());allv=[v for s in alls['sheets'] for v in s['violations']]
 assert len(allv)==3 and all(v.get('excluded') is True for v in allv),allv
 identity=lambda v:(v['type'],tuple(i['uuid'] for i in v['items']))
 assert set(map(identity,violations))==set(map(identity,allv)),'Exclusions must match exactly the raw three pin pairs'
 if not (audit/'drc-before-verification.json').exists():shutil.copyfile(audit/'drc.json',audit/'drc-before-verification.json')
 run=subprocess.run([c.CLI,'pcb','drc','--all-track-errors','--schematic-parity','--format','json','--output',str(audit/'drc.json'),str(out/'stratolink.kicad_pcb')],check=True,capture_output=True,text=True)
 (audit/'verification-drc.log').write_text(run.stdout+run.stderr)
 drc=json.loads((audit/'drc.json').read_text());assert not drc['unconnected_items'] and not drc['schematic_parity'];assert all(v['type']=='silk_over_copper' for v in drc['violations'])
 assert all(c.sha(out/name)==value for name,value in source_hashes.items()),'Verification changed source CAD'
 output=dict(candidate=str(out),pcb_sha256=c.sha(out/'stratolink.kicad_pcb'),schematic_sha256=c.sha(out/'stratolink.kicad_sch'),
  symbols_frozen_without_geometry_change=len(oldlibs),existing_instances_unchanged_except_library_id=len(oldinst),
  existing_wires_labels_junctions_text_exact=True,physical_pad_net_membership_exact=len(before_nets),
  normalized_authored_pcb_tree_identical_except_pintype=True,generated_fill_caches_refilled_on_both_scratch_copies=True,all_native_filled_polygon_geometry_identical=True,native_assigned_uuids_only_for_previously_uuidless_properties=sorted(generated_property_uuids),project_rules_identical_except_three_exact_marker_exclusions=True,identical_native_artwork_files=same,copper_export_serialization_differences=copper_serialization,
  erc_filtered_errors=0,erc_filtered_warnings=0,erc_raw_errors=2,erc_raw_warnings=1,erc_grounded_pin_exclusions=violations,drc_violations=dict(collections.Counter(v['type'] for v in drc['violations'])),drc_opens=0,drc_schematic_parity=0,
  script_sha256=c.sha(Path(__file__)),cleanup_script_sha256=c.sha(Path(__file__).with_name('clean_erc.py')))
 (audit/'verification.json').write_text(json.dumps(output,indent=2)+'\n');print(json.dumps(output,indent=2))
if __name__=='__main__':main()
