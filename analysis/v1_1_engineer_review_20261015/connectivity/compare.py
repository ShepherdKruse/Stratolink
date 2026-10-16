#!/usr/bin/env python3
"""Read-only native KiCad schematic/PCB electrical and footprint comparison."""
from pathlib import Path
import argparse,collections,hashlib,json,sys,xml.etree.ElementTree as ET
import pcbnew,wx
P=argparse.ArgumentParser();P.add_argument('--repo',type=Path,required=True);P.add_argument('--before',type=Path,required=True);P.add_argument('--after',type=Path,required=True);P.add_argument('--before-xml',type=Path,required=True);P.add_argument('--after-xml',type=Path,required=True);P.add_argument('--output',type=Path,required=True);a=P.parse_args()
sys.path.insert(0,str(a.repo/'analysis/v1_1_solar_attachments_20261012/review'));import check_solar_attachments as ast
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
paths=[d/('stratolink.'+e) for d in [a.before,a.after] for e in ['kicad_pcb','kicad_sch']];hashes={str(p):sha(p) for p in paths}
def children(e):return {'tag':e.tag,'attrib':dict(sorted(e.attrib.items())),'text':(e.text or '').strip(),'children':sorted([children(c) for c in e],key=lambda x:json.dumps(x,sort_keys=True))}
def components(p):
 r={}
 for c in ET.parse(p).findall('./components/comp'):
  r[c.get('ref')]={ch.tag:children(ch) for ch in c if ch.tag not in ['sheetpath','tstamps']}
 return r
def diffdict(x,y):return [{'key':list(k) if isinstance(k,tuple) else k,'before':x.get(k),'after':y.get(k)} for k in sorted(x.keys()|y.keys()) if x.get(k)!=y.get(k)]
xn=[ast.node_netlist(p) for p in [a.before_xml,a.after_xml]];xc=[components(p) for p in [a.before_xml,a.after_xml]]
sch=[ast.parse((p/'stratolink.kicad_sch').read_text()) for p in [a.before,a.after]]
schcats={k:[ast.nodes(s,k) for s in sch] for k in sorted({n[0] for s in sch for n in s if isinstance(n,list)})}
changedcats={k:{'before_count':len(v[0]),'after_count':len(v[1]),'order_only':sorted(map(repr,v[0]))==sorted(map(repr,v[1]))} for k,v in schcats.items() if v[0]!=v[1]}
ss=[{ast.prop(s,'Reference'):s for s in ast.nodes(t,'symbol')} for t in sch]
ssdiff=[]
for ref in sorted(ss[0].keys()|ss[1].keys()):
 o,n=[s.get(ref)for s in ss]
 if o!=n:
  old={k:ast.nodes(o,k) for k in {i[0] for i in o if isinstance(i,list)}} if o else {};new={k:ast.nodes(n,k) for k in {i[0] for i in n if isinstance(i,list)}} if n else {}
  ssdiff.append({'ref':ref,'changes':diffdict(old,new)})
app=wx.App(False);boards=[pcbnew.LoadBoard(str(p/'stratolink.kicad_pcb')) for p in [a.before,a.after]]
for b in boards:b.BuildConnectivity()
def fpdata(f):
 return {'uuid':f.m_Uuid.AsString(),'fpid':str(f.GetFPID().GetLibItemName())+'|'+str(f.GetFPID().GetLibNickname()),'value':f.GetValue(),'fields':{v.GetName():v.GetText()for v in f.GetFields()},'attributes':f.GetAttributes(),'sheetname':f.GetSheetname(),'sheetfile':f.GetSheetfile(),'path':f.GetPath().AsString()}
def pad(p):
 return {'number':p.GetNumber(),'net':p.GetNetname(),'local_xy_nm':list(p.GetFPRelativePosition()),'local_angle_deg':round(p.GetFPRelativeOrientation().AsDegrees()%360,6),'size_nm':list(p.GetSize()),'drill_nm':list(p.GetDrillSize()),'offset_nm':list(p.GetOffset()),'shape':int(p.GetShape()),'attribute':int(p.GetAttribute()),'layers':p.GetLayerSet().FmtHex(),'round_ratio':p.GetRoundRectRadiusRatio(),'chamfer_ratio':p.GetChamferRectRatio(),'chamfer_positions':p.GetChamferPositions()}
def pose(f):return {'x_mm':f.GetPosition().x/1e6,'y_mm':f.GetPosition().y/1e6,'angle_deg':f.GetOrientationDegrees()%360,'layer':f.GetLayerName()}
fps=[{f.GetReference():f for f in b.GetFootprints()} for b in boards];pd=[{(f.GetReference(),p.m_Uuid.AsString()):pad(p) for f in b.GetFootprints() for p in f.Pads()} for b in boards]
pm=[{k:[p.GetNetname() for p in v] for k,v in ast.pad_groups(b).items()} for b in boards]
fpdiff=diffdict({r:fpdata(f)for r,f in fps[0].items()},{r:fpdata(f)for r,f in fps[1].items()})
poses=diffdict({r:pose(f)for r,f in fps[0].items()},{r:pose(f)for r,f in fps[1].items()})
paddiff=diffdict(*pd)
conn=[]
for b in boards:
 c=b.GetConnectivity(); conn.append({(f.GetReference(),p.m_Uuid.AsString()):sorted([list(k) for k in ast.connected_keys(c,p)])for f in b.GetFootprints() for p in f.Pads()})
# Test actual connected-pad sets against all named pads of a net. Unnamed pads are independent.
physical=[]
for side,b in zip(['before','after'],boards):
 bynet=collections.defaultdict(set)
 for f in b.GetFootprints():
  for p in f.Pads():
   if p.GetNetname():bynet[p.GetNetname()].add((f.GetReference(),p.GetNumber()))
 c=b.GetConnectivity();mismatch=[]
 for f in b.GetFootprints():
  for p in f.Pads():
   if not p.GetNetname():continue
   connected=ast.connected_keys(c,p);expected=bynet[p.GetNetname()]
   if expected!=connected:mismatch.append({'ref':f.GetReference(),'pin':p.GetNumber(),'uuid':p.m_Uuid.AsString(),'net':p.GetNetname(),'missing':[list(k)for k in sorted(expected-connected)],'unexpected':[list(k)for k in sorted(connected-expected)]})
 physical.append({'side':side,'native_unconnected_count':c.GetUnconnectedCount(False),'pad_connectivity_mismatches':mismatch})
parity=[]
for idx in [0,1]:
 misses=[]
 for key,names in pm[idx].items():
  schematic=xn[idx].get(key)
  expected=schematic[0] if schematic else ''
  if set(names)!={expected}:misses.append({'ref_pin':list(key),'schematic':schematic,'pcb_names':names})
 missingpcb=[{'ref_pin':list(k),'schematic':v} for k,v in xn[idx].items() if k not in pm[idx] and k[0] in fps[idx]]
 parity.append({'side':['before','after'][idx],'pad_mapping_mismatches':misses,'schematic_pins_missing_board_pad':missingpcb})
# Classify known native XML vs PCB escape syntax and board-only suspension holes.
for entry in parity:
 entry['net_escape_equivalents']=[];entry['board_only_suspension_pads']=[];entry['unexplained_pad_mapping_mismatches']=[]
 for mismatch in entry['pad_mapping_mismatches']:
  if mismatch['schematic'] and {n.replace('{slash}','/') for n in mismatch['pcb_names']}=={mismatch['schematic'][0]}:
   entry['net_escape_equivalents'].append(mismatch['ref_pin'])
  elif mismatch['ref_pin']in[['H1','1'],['H2','1']]and mismatch['schematic']is None and set(mismatch['pcb_names'])=={'GND'}:
   entry['board_only_suspension_pads'].append(mismatch['ref_pin'])
  else:entry['unexplained_pad_mapping_mismatches'].append(mismatch)
# Pad fabrication rules must be reviewed even if dimensions and net names match.
trees=[ast.parse((p/'stratolink.kicad_pcb').read_text())for p in[a.before,a.after]]
pad_rule_sets=[]
for t in trees:
 rules={}
 for f in ast.nodes(t,'footprint'):
  for p in ast.nodes(f,'pad'):
   rules[(ast.prop(f,'Reference'),ast.field(p,'uuid'))]=[x for x in p if not(isinstance(x,list)and x and x[0]in['at','layers','net','uuid'])]
 pad_rule_sets.append(rules)
libpart_changes=diffdict(*[{(l.get('lib'),l.get('part')):children(l)for l in ET.parse(p).findall('./libparts/libpart')}for p in[a.before_xml,a.after_xml]])
report={'hashes':hashes,'kicad':pcbnew.GetBuildVersion(),'schematic':{'node_counts':[len(v)for v in xn],'net_name_counts':[len(set(v[0] for v in n.values()))for n in xn],'component_counts':[len(v)for v in xc],'logical_node_changes':diffdict(*xn),'component_changes':diffdict(*xc),'library_part_changes':libpart_changes,'changed_top_level_categories':changedcats,'symbol_changes':ssdiff},'pcb':{'footprint_counts':[len(v)for v in fps],'physical_pad_counts':[len(v)for v in pd],'logical_pad_counts':[len(v)for v in pm],'footprint_metadata_changes':fpdiff,'footprint_pose_changes':poses,'physical_pad_changes':paddiff,'pad_fabrication_metadata_changes':diffdict(*pad_rule_sets),'pad_to_net_changes':diffdict(*pm),'connected_pad_set_changes':diffdict(*conn),'physical_connectivity':physical,'schematic_parity':parity},'source_bytes_unchanged':all(sha(Path(p))==h for p,h in hashes.items()),'limitations':['Checks native saved copper connectivity without refill or save. Root DRC will test strict project settings and refill separately.','Numeric net codes ignored; comparisons use physical pad UUID, reference/pin number, named net membership and connected pad sets.','Electrical connectivity checks do not certify RF performance, component clearance, manufacturing or assembly.']}
dump(a.output,report)
print(json.dumps({'schematic_node_counts':report['schematic']['node_counts'],'node_changes':len(report['schematic']['logical_node_changes']),'component_changes':len(report['schematic']['component_changes']),'top_categories':changedcats,'pcb_counts':[report['pcb'][k]for k in ['footprint_counts','physical_pad_counts','logical_pad_counts']],'metadata_changes':len(fpdiff),'pad_changes':len(paddiff),'net_changes':len(report['pcb']['pad_to_net_changes']),'physical':[{'side':v['side'],'opens':v['native_unconnected_count'],'bad_pads':len(v['pad_connectivity_mismatches'])}for v in physical],'parity':parity,'source_bytes_unchanged':report['source_bytes_unchanged']},indent=2))
