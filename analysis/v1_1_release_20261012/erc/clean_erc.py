#!/usr/bin/env python3
"""Freeze embedded symbols and correct electrical intent in a fresh scratch copy."""
from pathlib import Path
import argparse,copy,hashlib,importlib.util,json,math,re,shutil,subprocess,uuid,xml.etree.ElementTree as ET
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sp=importlib.util.spec_from_file_location('scoped_edit',ROOT/'analysis/v1_1_ground_20261012/build_candidate.py')
h=importlib.util.module_from_spec(sp);sp.loader.exec_module(h);a=h.cad
CLI='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli';LIB='Stratolink_v1p1_Symbols'
TYPES={
 'U1':{'1':'power_in','2':'power_in','3':'input','4':'input','5':'input','6':'input','7':'input','8':'power_out','9':'input','10':'input','11':'input','12':'input','13':'output','14':'power_out','15':'power_in','16':'bidirectional','17':'input','18':'power_in','19':'power_out','20':'bidirectional','21':'power_in'},
 'U3':{'1':'power_in','2':'output','3':'input','4':'output','5':'input','6':'power_in','7':'power_in','8':'power_in','9':'input','10':'power_in','11':'input','12':'power_in','13':'output','14':'power_out','15':'input','16':'bidirectional','17':'input','18':'input'},
 'U4':{'1':'power_in','2':'input','3':'power_in','4':'input','5':'input','6':'output','7':'bidirectional','8':'input'},
 'U6':{'1':'power_in','2':'no_connect','3':'power_in','4':'input','5':'open_collector','6':'bidirectional'},
 'AE1':{'1':'passive'},'AE2':{'1':'passive'},
}
# Explicit reviewed unused pins; unconnected net alone is never taken as permission.
UNUSED={'U2':{'1','2','13','14','15','16','27'},'U3':{'4','13','14','15','18'},'U4':{'6'},'U6':{'2'},'U7':{'11'},'J20':{'6'}}
GROUNDED_EXCLUSIONS={
 ('U5','C2'):('error','TMP117 ALERT is intentionally unavailable and grounded. TI TMP117 datasheet section 8.2.1 explicitly permits grounding ALERT when unused. Open-drain pin type retained; this exact marker is contention with the external GND PWR_FLAG, not a driven-high circuit.'),
 ('U6','5'):('error','LTR-390UV INT is an unused open-drain output tied to GND, with no pull-up or driven-high source on the output. Electrical inference: its sink cannot contend with GND; LiteOn identifies open-drain operation but an explicit recommendation to ground was not located. Interrupt functionality is unavailable; keep LS_INT_EN disabled. Only this exact GND PWR_FLAG marker is excluded.'),
 ('U7','3'):('warning','LIS2DH12 SDO/SA0 is grounded to select I2C address 0x18 with CS high, as specified in ST datasheet section 6.1.1. Bidirectional type retained for its SPI role. Only this exact GND PWR_FLAG marker is excluded. Firmware follow-up: disable internal SDO pull-up using CTRL_REG0 SDO_PU_DISC while preserving required other bits.'),
}

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def uid(kind):return str(uuid.uuid5(uuid.NAMESPACE_URL,'stratolink-v1p1-erc/'+kind))
def q(s):return json.dumps(s,ensure_ascii=False)
def sections(text,kind,depth=1):
 return [(s,e,text[s:e],a.parse(text[s:e])) for s,e,d in h.spans(text) if d==depth and re.match(r'^\('+re.escape(kind)+r'[\s)]',text[s:e])]
def direct(text,kind):return [(s,e,b,n) for s,e,b,n in sections(text,kind) if n[0]==kind]
def replace_atom_node(block,kind,value):
 changes=[(s,e,'('+kind+' '+q(value)+')') for s,e,b,n in direct(block,kind)]
 assert len(changes)==1,(kind,changes)
 return h.replace(block,changes)
def pin_nodes(lib):
 result={}
 for unit in a.nodes(lib,'symbol'):
  for pin in a.nodes(unit,'pin'):
   number=a.scalar(pin,'number');assert number not in result;result[number]=pin
 return result

def rename_library(block,newname,topname=None):
 old=a.parse(block)[1];base=old.split(':')[-1];edits=[]
 for s,e,b,n in direct(block,'symbol'):
  child=n[1];assert child.startswith(base+'_'),(old,child)
  replacement=newname+child[len(base):]
  edits.append((s,e,b.replace('(symbol '+q(child),'(symbol '+q(replacement),1)))
 block=h.replace(block,edits)
 return block.replace('(symbol '+q(old),'(symbol '+q(topname or newname),1)

def pin_position(sym,pin):
 sx,sy,angle=map(float,a.one(sym,'at'));px,py=map(float,a.one(pin,'at')[:2]);r=math.radians(angle)
 assert not a.one(sym,'mirror'),'Mirror handling needs explicit review'
 return [round(sx+px*math.cos(r)-py*math.sin(r),6),round(sy-px*math.sin(r)-py*math.cos(r),6)]

def netmap(path):
 result={};groups=[];types={}
 for net in ET.parse(path).findall('.//nets/net'):
  pins=[]
  for p in net.findall('node'):
   key=(p.get('ref'),p.get('pin'))
   if key[0].startswith('#'):continue
   assert key not in result;result[key]=net.get('name');types[key]=p.get('pintype');pins.append(key)
  if pins:groups.append(tuple(sorted(pins)))
 return result,set(groups),types

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--candidate',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
 src=args.candidate.resolve();out=args.output.resolve();assert src!=out and src not in out.parents and not out.exists()
 protected={str(p.relative_to(src)):sha(p) for p in src.rglob('*') if p.is_file()}
 shutil.copytree(src,out,symlinks=False);audit=out/'erc-audit';audit.mkdir(exist_ok=False)
 def run(name,cmd):
  r=subprocess.run(cmd,capture_output=True,text=True,check=True);(audit/(name+'.log')).write_text(r.stdout+r.stderr)
 sch=out/'stratolink.kicad_sch';pcb=out/'stratolink.kicad_pcb'
 before=audit/'before';before.mkdir()
 for name in ['stratolink.kicad_pcb','stratolink.kicad_sch','stratolink.kicad_pro']:shutil.copyfile(out/name,before/name)
 run('before-netlist',[CLI,'sch','export','netlist','--format','kicadxml','--output',str(audit/'before-netlist.xml'),str(sch)])
 run('before-erc',[CLI,'sch','erc','--format','json','--output',str(audit/'before-erc.json'),str(sch)])
 oldnets,oldgroups,oldtypes=netmap(audit/'before-netlist.xml')
 text=sch.read_text();tree=a.parse(text);root_uuid=a.scalar(tree,'uuid');inst={a.prop(n,'Reference'):(s,e,b,n) for s,e,b,n in direct(text,'symbol')}
 ls=direct(text,'lib_symbols')[0];libblocks={n[1]:(s,e,b,n) for s,e,b,n in direct(ls[2],'symbol')}
 assignments={};typemaps={}
 for ref,table in TYPES.items():
  oldid=a.scalar(inst[ref][3],'lib_id');existing=typemaps.get(oldid);assert existing is None or existing==table;typemaps[oldid]=table
 changes=[];embedded=[];local=[];pin_changes=[];old_to_new={}
 for oldid,(_,_,block,libnode) in libblocks.items():
  name=re.sub(r'[^A-Za-z0-9_]+','_',oldid);assert name not in old_to_new.values();old_to_new[oldid]=name
  edits=[]
  if oldid in typemaps:
   pins=pin_nodes(libnode);table=typemaps[oldid];assert pins.keys()==table.keys(),(oldid,pins.keys(),table.keys())
   for start,end,depth in h.spans(block):
    n=a.parse(block[start:end])
    if not n or n[0]!='pin' or a.scalar(n,'number') not in table:continue
    number=a.scalar(n,'number');before=n[1];after=table[number]
    if before!=after:
     old=block[start:end];edits.append((start,end,old.replace('(pin '+before+' ','(pin '+after+' ',1)))
     pin_changes.append(dict(library=oldid,number=number,name=a.scalar(n,'name'),before=before,after=after))
  block=h.replace(block,edits)
  embedded.append(rename_library(block,name,LIB+':'+name));local.append(rename_library(block,name))
 for ref,(s,e,b,n) in inst.items():
  oldid=a.scalar(n,'lib_id');changes.append((s,e,replace_atom_node(b,'lib_id',LIB+':'+old_to_new[oldid])))
 nc=[]
 existingnc={tuple(map(float,a.one(n,'at'))) for n in a.nodes(tree,'no_connect')}
 for ref,numbers in UNUSED.items():
  sym=inst[ref][3];pins=pin_nodes(libblocks[a.scalar(sym,'lib_id')][3])
  for number in sorted(numbers,key=int):
   key=(ref,number);net=oldnets.get(key);assert net and net.startswith('unconnected-'),('Not actually unused',key,net)
   assert sum(v==net for v in oldnets.values())==1
   pos=pin_position(sym,pins[number])
   if tuple(pos) in existingnc:continue
   nc.append(dict(ref=ref,pin=number,at=pos,uuid=uid('NC/'+ref+'/'+number)))
 # Source-entry flags represent actual external power and the supply after the passive filter.
 targets=[('J1','1','+SOLAR'),('J1','2','GND'),('FB1','1','Net-(U3-VCC)')]
 # VBAT is a power terminal, not signal-bidirectional IO. The official KiCad
 # BQ25570 symbol also uses power_in for pin18. Declare its actual reservoir
 # supply and retain power-drive checking rather than suppress a pin conflict.
 reservoir_net=oldnets.get(('C5','1'))
 assert reservoir_net in ('Net-(U1-VBAT)','/VBAT') and oldnets.get(('U1','18'))==reservoir_net
 assert oldnets.get(('C5','2'))=='GND'
 assert a.prop(inst['U1'][3],'Manufacturer_Part_Number')=='BQ25570RGRR'
 targets.append(('C5','1',reservoir_net))
 if 'U8' in inst:
  # Additionally guard the reviewed balancer's topology when it is present.
  assert a.prop(inst['U8'][3],'Manufacturer_Part_Number')=='TLV8801DBVT'
  assert all(oldnets.get(key)=='/VBAT' for key in [('C5','1'),('U1','18'),('U8','5'),('C22','1'),('R24','1')]),'Unexpected balancer supply topology'
  assert all(oldnets.get(key)=='GND' for key in [('U8','2'),('C22','2')])
 power_path=Path('/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols/power.kicad_sym')
 power=next(b for s,e,b,n in direct(power_path.read_text(),'symbol') if n[1]=='PWR_FLAG')
 flagname='PWR_FLAG';embedded.append(rename_library(power,flagname,LIB+':'+flagname));local.append(rename_library(power,flagname))
 added_flags=[];flagtexts=[]
 for index,(ref,number,netname) in enumerate(targets,101):
  assert oldnets[(ref,number)]==netname,(ref,number,oldnets[(ref,number)])
  symbol=inst[ref][3];pins=pin_nodes(libblocks[a.scalar(symbol,'lib_id')][3]);x,y=pin_position(symbol,pins[number]);flagref='#FLG'+str(index)
  assert flagref not in inst
  added_flags.append(dict(reference=flagref,at=[x,y],net=netname,connection=ref+'.'+number,
   rationale='Actual harvester/storage reservoir at C5.1. U1.VBAT is modeled as power_in, consistent with KiCad power-pin semantics and its official BQ25570 symbol; this is not a signal-bidirectional terminal.' if ref=='C5' else 'Actual external solar power/return or supply after passive GNSS filter.'))
  flagtexts.append(f'''(symbol (lib_id "{LIB}:PWR_FLAG") (at {x} {y} 0) (unit 1)
    (exclude_from_sim no) (in_bom no) (on_board no) (dnp no) (uuid "{uid(flagref)}")
    (property "Reference" "{flagref}" (at {x} {y+1.905} 0) (effects (font (size 1.27 1.27)) (hide yes)))
    (property "Value" "PWR_FLAG" (at {x} {y-3.81} 0) (effects (font (size 1.27 1.27))))
    (property "Footprint" "" (at {x} {y} 0) (effects (font (size 1.27 1.27)) (hide yes)))
    (property "Datasheet" "" (at {x} {y} 0) (effects (font (size 1.27 1.27)) (hide yes)))
    (pin "1" (uuid "{uid(flagref+'/1')}"))
    (instances (project "stratolink" (path "/{root_uuid}" (reference "{flagref}") (unit 1)))))''')
 changes.append((ls[0],ls[1],'(lib_symbols\n'+'\n'.join(embedded)+'\n)'))
 text=h.replace(text,changes);extra=['(no_connect (at %s %s) (uuid %s))'%(r['at'][0],r['at'][1],q(r['uuid'])) for r in nc]+flagtexts
 text=text.rstrip()[:-1]+'\n'+'\n'.join(extra)+'\n)\n';sch.write_text(text)
 library=out/'lib'/(LIB+'.kicad_sym');library.write_text('(kicad_symbol_lib (version 20250114) (generator "kicad_symbol_editor")\n'+'\n'.join(local)+'\n)\n')
 table=out/'sym-lib-table';old=table.read_text();assert '(name "'+LIB+'")' not in old
 table.write_text(old.rstrip()[:-1]+'\n(lib (name "'+LIB+'")(type "KiCad")(uri "${KIPRJMOD}/lib/'+LIB+'.kicad_sym")(options "")(descr "Frozen embedded v1.1 symbols; datasheet-derived electrical types"))\n)\n')
 run('after-netlist',[CLI,'sch','export','netlist','--format','kicadxml','--output',str(audit/'after-netlist.xml'),str(sch)])
 newnets,newgroups,newtypes=netmap(audit/'after-netlist.xml');assert oldnets==newnets,'Physical pad-net membership changed';assert oldgroups==newgroups
 # Metadata only: preserve PCB bytes outside pintype fields, including every physical feature.
 original=pcb.read_text();edits=[];pad_changes=[]
 for s,e,block,f in direct(original,'footprint'):
  ref=a.prop(f,'Reference');inside=[]
  for ps,pe,pb,p in direct(block,'pad'):
   key=(ref,p[1]);before=a.scalar(p,'pintype');after=newtypes.get(key)
   if before is not None and after is not None and before!=after:
    inside.append((ps,pe,replace_atom_node(pb,'pintype',after)));pad_changes.append(dict(ref=ref,pin=p[1],before=before,after=after))
  if inside:edits.append((s,e,h.replace(block,inside)))
 pcb.write_text(h.replace(original,edits))
 run('raw-erc',[CLI,'sch','erc','--format','json','--output',str(audit/'raw-erc.json'),str(sch)])
 raw=json.loads((audit/'raw-erc.json').read_text());violations=[v for sheet in raw['sheets'] for v in sheet['violations']]
 # Serialize exactly the three reviewed pin-pair markers. Do not alter ERC severity
 # matrices or pin types to hide intended grounded open-drain/address connections.
 assert len(violations)==len(GROUNDED_EXCLUSIONS),('Unexpected remaining ERC findings',violations)
 exclusions=[];seen=set();sheetpath='/'+root_uuid
 for v in violations:
  assert v['type']=='pin_to_pin' and len(v['items'])==2,v
  m=re.match(r'^Symbol (\S+) Pin (\S+) ',v['items'][0]['description']);assert m,v
  key=m.groups();assert key in GROUNDED_EXCLUSIONS and key not in seen,(key,v);seen.add(key)
  severity,reason=GROUNDED_EXCLUSIONS[key];assert v['severity']==severity
  assert v['items'][1]['uuid']==uid('#FLG102/1'),v
  ref,number=key;sym=inst[ref][3];pin=pin_nodes(libblocks[a.scalar(sym,'lib_id')][3])[number]
  assert oldnets[key]=='GND';pos=pin_position(sym,pin)
  pin_uuid=a.scalar(next(n for n in a.nodes(sym,'pin') if n[1]==number),'uuid')
  assert pin_uuid==v['items'][0]['uuid']
  # KiCad 10 SCH IU = 10000/mm. Derive position from the schematic, avoiding
  # the CLI JSON report's observed scale discrepancy for schematic coordinates.
  marker='|'.join(['pin_to_pin',str(round(pos[0]*10000)),str(round(pos[1]*10000)),pin_uuid,uid('#FLG102/1'),sheetpath,sheetpath,sheetpath])
  exclusions.append([marker,reason])
 pro=out/'stratolink.kicad_pro';project=json.loads(pro.read_text());assert not project['erc'].get('erc_exclusions'),'Pre-existing exclusions require separate review'
 project['erc']['erc_exclusions']=exclusions;pro.write_text(json.dumps(project,indent=2)+'\n')
 run('after-erc',[CLI,'sch','erc','--format','json','--exit-code-violations','--output',str(audit/'after-erc.json'),str(sch)])
 run('all-erc',[CLI,'sch','erc','--severity-all','--format','json','--output',str(audit/'all-erc.json'),str(sch)])
 run('drc',[CLI,'pcb','drc','--schematic-parity','--format','json','--output',str(audit/'drc.json'),str(pcb)])
 assert {str(p.relative_to(src)):sha(p) for p in src.rglob('*') if p.is_file()}==protected,'Input changed during cleanup'
 report=dict(source=str(src),candidate=str(out),source_hashes=protected,pin_type_changes=pin_changes,pcb_pin_metadata_changes=pad_changes,
    no_connect_flags=nc,power_flags=added_flags,library_map=old_to_new,physical_net_membership_unchanged=True,physical_pcb_unchanged_except_pin_type_metadata=True,
    files={str(p.relative_to(out)):sha(p) for p in [pcb,sch,pro,table,library]},erc_marker_exclusions=exclusions,
    erc_before=json.loads((audit/'before-erc.json').read_text()),erc_raw=raw,erc_after=json.loads((audit/'after-erc.json').read_text()),erc_all=json.loads((audit/'all-erc.json').read_text()))
 (audit/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'candidate':str(out),'pin_type_changes':len(pin_changes),'nc_flags':len(nc),'power_flags':added_flags,'erc_after':[(v['type'],v['description'],v['items']) for s in report['erc_after']['sheets'] for v in s['violations']]},indent=2))
if __name__=='__main__':main()
