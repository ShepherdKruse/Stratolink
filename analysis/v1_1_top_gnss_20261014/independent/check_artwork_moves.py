#!/usr/bin/env python3
"""Verify exact declared rigid label translations and preserve all other artwork.
Net-assigned copper additions/removals are listed for the separate connectivity,
etch and visual reviews. They never authorize arbitrary decorative edits.
"""
from pathlib import Path
import argparse,copy,hashlib,json,sys
p=argparse.ArgumentParser(description=__doc__)
for name in ['repo','before','after','plan','output']:p.add_argument('--'+name,type=Path,required=True)
a=p.parse_args();assert not a.output.exists(),a.output
sys.path.insert(0,str(a.repo/'analysis/v1_1_solar_attachments_20261012/review'));import check_solar_attachments as audit
raw=[p.read_bytes()for p in [a.before,a.after]];trees=[audit.parse(x.decode())for x in raw];plan=json.loads(a.plan.read_text());assert hashlib.sha256(raw[0]).hexdigest()==plan['source_sha256']
def eq(x,y):
 if isinstance(x,list)or isinstance(y,list):return isinstance(x,list)and isinstance(y,list)and len(x)==len(y)and all(eq(u,v)for u,v in zip(x,y))
 if x==y:return True
 try:return abs(float(x)-float(y))<=.0000011
 except(ValueError,TypeError):return False
def translate(tree,delta):
 t=copy.deepcopy(tree)
 def move(n):
  if not isinstance(n,list)or not n:return
  if n[0]in['xy','at','start','end','mid','center']:n[1]=str(float(n[1])+delta[0]);n[2]=str(float(n[2])+delta[1])
  else:
   for c in n:move(c)
 move(t);return t
assert audit.nodes(trees[0],'group')==audit.nodes(trees[1],'group'),'Group membership changed'
groups={g[1]:g for g in audit.nodes(trees[0],'group')};moved={}
for group,delta in plan['moves'].items():
 assert len(delta)==2 and any(v!=0 for v in delta),(group,delta)
 for uid in audit.nodes(groups[group],'members')[0][1:]:
  assert uid not in moved,uid;moved[uid]=delta
shapes=[audit.keyed([n for n in tree if isinstance(n,list)and n and str(n[0]).startswith('gr_')])for tree in trees]
text_changes=plan.get('text_changes',{})
assert not(set(text_changes)&set(moved)), 'Text edits cannot also be translated'
net_changes=[];preserved=0
for uid in sorted(shapes[0].keys()|shapes[1].keys()):
 old,new=(s.get(uid)for s in shapes)
 if uid in text_changes:
  edit=text_changes[uid];assert set(edit)=={'before','after'} and edit['before']!=edit['after']
  assert old is not None and new is not None and old[0]==new[0]=='gr_text' and audit.field(old,'layer')in['F.Fab','B.Fab']
  assert old[1]==edit['before']and new[1]==edit['after'],('Wrong exact assembly note edit',uid)
  expected=copy.deepcopy(old);expected[1]=edit['after'];assert expected==new,('Unexpected assembly note geometry/style edit',uid)
 elif uid in moved:
  assert old is not None and new is not None and eq(translate(old,moved[uid]),new),('Nonrigid or wrong artwork translation',uid)
 elif old is not None and new is not None and old==new:preserved+=1
 else:
  vals=[v for v in [old,new]if v is not None]
  assert all(audit.field(v,'net') for v in vals),('Undeclared decorative artwork change',uid)
  net_changes.append({'uuid':uid,'before_net':audit.field(old,'net')if old else None,'after_net':audit.field(new,'net')if new else None,'before_layer':audit.field(old,'layer')if old else None,'after_layer':audit.field(new,'layer')if new else None})
assert set(moved)<=shapes[0].keys()
assert set(text_changes)<=shapes[0].keys()
assert raw==[p.read_bytes()for p in [a.before,a.after]]
r={'before_pcb_sha256':hashlib.sha256(raw[0]).hexdigest(),'pcb_sha256':hashlib.sha256(raw[1]).hexdigest(),'plan_sha256':hashlib.sha256(a.plan.read_bytes()).hexdigest(),'exact_group_moves_mm':plan['moves'],'exact_assembly_text_edits':text_changes,'rigidly_translated_graphics':len(moved),'unchanged_other_drawing_count':preserved,'all_other_unnetted_artwork_unchanged':True,'group_membership_unchanged':True,'net_assigned_copper_changes_for_separate_review':net_changes,'source_bytes_unchanged':True}
a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items()if k!='net_assigned_copper_changes_for_separate_review'},indent=2))
