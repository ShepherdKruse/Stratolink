#!/usr/bin/env python3
"""Pin the independently inspected two-mask / straight-wire / duplicate scope.

Run with KiCad's Python after component candidates are frozen. This script
checks concrete dimensions and property identity before writing the inventory.
"""
from pathlib import Path
import importlib.util,json,sys
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
spec=importlib.util.spec_from_file_location('native_review',HERE/'verify_native.py');v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v);a=v.a

def main():
 manifest=json.loads((HERE/'baseline-manifest.json').read_text());base=Path(manifest['snapshot_path'])
 assembly=json.loads((HERE.parent/'assembly/candidate.json').read_text());source=Path(assembly['candidate'])
 mask=json.loads((HERE.parent/'mask/candidate.json').read_text());masksource=Path(mask['candidate'])
 for name,sha in assembly['files'].items():assert v.digest(source/name)==sha,(name,'Assembly candidate changed')
 old,new,masked=[a.parse((p/'stratolink.kicad_pcb').read_text()) for p in [base,source,masksource]]
 scope=dict(footprints={},schematic_properties={},changed_segments=[],added_segments=[],removed_segments=['fa277942-2f97-4c70-a150-464479c3b65e'],removed_segment_objects={},mask_graphics={},new_library_files={},expected_new_drc={})
 for ref,length,maxlength,lib in [('AE1',82,87,'Stratolink_LoRa_Wire_PTH_D1p0'),('AE2',48,49,'Stratolink_GNSS_Wire_PTH_D1p0')]:
  aa,bb=[next(f for f in a.nodes(t,'footprint') if a.prop(f,'Reference')==ref) for t in [old,new]]
  assert bb[1]=='lib:'+lib
  for field in ['at','layer','uuid','pad','attr']:
   assert a.nodes(aa,field)==a.nodes(bb,field),(ref,field)
  pa,pb=[{p[1]:p for p in a.nodes(f,'property')} for f in [aa,bb]];assert pa.keys()==pb.keys()
  for name in pa:
   if name=='Reference':assert pa[name]==pb[name]
   else:
    assert name in ['Value','Datasheet','Description'];assert pa[name][:2]+pa[name][3:]==pb[name][:2]+pb[name][3:]
  assert pb['Datasheet'][2]=='https://stratolink.org/docs/hardware#antennas-and-suspension'
  fab=[x for x in a.nodes(bb,'fp_line') if a.field(x,'layer')=='F.Fab'];assert len(fab)==1
  assert a.nodes(fab[0],'start')==[['start','0','0']];assert a.nodes(fab[0],'end')==[['end',str(length),'0']]
  assert a.nodes(fab[0],'stroke')==[['stroke',['width','0.321'],['type','solid']]]
  courtyard=[x for x in a.nodes(bb,'fp_line') if a.field(x,'layer')=='F.CrtYd'];assert len(courtyard)==4
  points=[[-1.25,-1.25],[maxlength,-1.25],[maxlength,1.25],[-1.25,1.25]]
  for i,line in enumerate(courtyard):
   assert [float(x) for x in a.nodes(line,'start')[0][1:]]==points[i]
   assert [float(x) for x in a.nodes(line,'end')[0][1:]]==points[(i+1)%4]
  ma,mb=[a.nodes(f,'model') for f in [aa,bb]];assert len(ma)==len(mb)==1;assert ma[0][2:]==mb[0][2:]
  assert mb[0][1]=='${KIPRJMOD}/lib/Stratolink_Wire_%dmm_D0p321_Nominal.step'%length
  fields=['descr','property','fp_line','model']
  scope['footprints'][ref]=dict(library_id=bb[1],fields=fields,before={f:a.nodes(aa,f) for f in fields},after={f:a.nodes(bb,f) for f in fields})
  expected_model=(base/'lib/gps.step').read_text();assert expected_model.count('0.0456')==5
  filename='Stratolink_Wire_%dmm_D0p321_Nominal.step'%length
  expected_model=expected_model.replace('0.0456',format(length/1000,'.4f')).replace("FILE_NAME('dump.step'","FILE_NAME('"+filename+"'")
  assert (source/'lib'/filename).read_text()==expected_model
 for ref in ['AE1','AE2']:
  aa,bb=[next(s for s in a.nodes(a.parse((p/'stratolink.kicad_sch').read_text()),'symbol') if a.prop(s,'Reference')==ref) for p in [base,source]]
  props={}
  for name in ['Value','Footprint','Datasheet','Description']:
   pa,pb=[next(p for p in a.nodes(s,'property') if p[1]==name) for s in [aa,bb]]
   assert pa[:2]+pa[3:]==pb[:2]+pb[3:];props[name]=dict(before=pa[2],after=pb[2])
  scope['schematic_properties'][ref]=props
 for filename in assembly['new_library_files']:
  assert filename.startswith('lib/');scope['new_library_files'][filename[4:]]=v.digest(source/filename)
 assert len(scope['new_library_files'])==4
 for uid,layer in [('19552f78-8bc8-5d58-a252-cce4c7aa3763','F.Mask'),('65f5aa32-1dfc-539e-ac84-add1df7c2354','B.Mask')]:
  rect=next(x for x in a.nodes(masked,'gr_rect') if a.field(x,'uuid')==uid)
  assert a.field(rect,'layer')==layer and a.field(rect,'fill')=='yes'
  assert a.nodes(rect,'start')==[['start','52','28']] and a.nodes(rect,'end')==[['end','78','88']]
  assert a.nodes(rect,'stroke')==[['stroke',['width','0'],['type','default']]]
  scope['mask_graphics'][uid]=rect
 for uid in scope['removed_segments']:scope['removed_segment_objects'][uid]=next(x for x in a.nodes(old,'segment') if a.field(x,'uuid')==uid)
 expected=json.loads((HERE/'expected-no-mask-findings.json').read_text())['non_bridge_findings']
 for mode in ['project','prior-uniform','retained-netclasses','original-edge-policy','mask-bridge-enabled']:
  scope['expected_new_drc'][mode]=dict(violations=expected,unconnected_items=[],schematic_parity=[])
 (HERE/'approved-scope.json').write_text(json.dumps(scope,indent=2)+'\n');print('Explicit reviewed scope written')
if __name__=='__main__':main()
