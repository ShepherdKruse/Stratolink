#!/usr/bin/env python3
"""Build a reviewable, UNROUTED active-balancer pilot in isolated scratch.

Run with KiCad's bundled Python. The existing circuit is copied from a frozen
commit; canonical hardware is never written. Existing geometry is preserved.
"""
from pathlib import Path
import importlib.util,json,subprocess,sys,uuid,re,hashlib
import pcbnew,wx
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
BASE='59979799c5809d636639084227d9fee75c8de1d9'
OUT=Path.home()/'Repositories/ai-working/scratch/stratolink-release-20261012/power/balancer-candidate'
CLI='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
spec=importlib.util.spec_from_file_location('prior',ROOT/'analysis/v1_1_ground_20261012/build_candidate.py');prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior);a=prior.cad
NS=uuid.UUID('419b6b15-df58-49ce-8a9f-e24a5b7e9927')
def uid(s):return str(uuid.uuid5(NS,s))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def boardnet(name):return name if name=='GND' else '/'+name
def prop(name,value,x=0,y=0,hide=False):
 return '(property %s %s (at %s %s 0) (effects (font (size 1 1))%s))'%(json.dumps(name,ensure_ascii=False),json.dumps(value,ensure_ascii=False),x,y,' (hide yes)' if hide else '')
def pin(num,name,typ,x,y,rot,length):
 return '(pin %s line (at %s %s %s) (length %s) (name %s (effects (font (size 1 1)))) (number "%s" (effects (font (size 1 1)))))'%(typ,x,y,rot,length,json.dumps(name,ensure_ascii=False),num)
def line(x1,y1,x2,y2):return '(polyline (pts (xy %s %s) (xy %s %s)) (stroke (width 0.2) (type default)) (fill (type none)))'%(x1,y1,x2,y2)
def symbol_lib(name,ref,value,fp,ds,description,graphics,pins):
 return '(symbol "%s" (pin_names (offset 0.5)) (exclude_from_sim no) (in_bom yes) (on_board yes) %s (symbol "%s_0_1" %s) (symbol "%s_1_1" %s))'%(name,' '.join([prop('Reference',ref,0,7),prop('Value',value,0,-7),prop('Footprint',fp,hide=True),prop('Datasheet',ds,hide=True),prop('Description',description,hide=True)]),name,graphics,name,pins)
OPNAME='TLV8801DBVT';CAPNAME='DMF4B5R5G105M3DTA0_3T'
OP=symbol_lib(OPNAME,'U',OPNAME,'Package_TO_SOT_SMD:SOT-23-5','https://www.ti.com/lit/ds/symlink/tlv8801.pdf','450nA typical nanopower amplifier; CAP-XX midpoint follower',line(-5.08,5.08,-5.08,-5.08)+line(-5.08,-5.08,5.08,0)+line(5.08,0,-5.08,5.08),' '.join([pin(1,'OUT','output',7.62,0,180,2.54),pin(2,'V-','power_in',0,-7.62,90,5.08),pin(3,'+','input',-7.62,2.54,0,2.54),pin(4,'-','input',-7.62,-2.54,0,2.54),pin(5,'V+','power_in',0,7.62,270,5.08)]))
# The outer pins deliberately retain Device:C's exact positions/numbers.
CAP=symbol_lib(CAPNAME,'C','1F','lib:DMF4B5R5G105M3DTA0','https://www.cap-xx.com','CAP-XX DMF dual cell; placed pin1 positive, pin2 negative, pin3 midpoint; hand-install', ''.join(line(-2,y,2,y) for y in [-1.905,-.635,.635,1.905])+line(0,-.635,0,.635)+line(-2.54,0,0,0),' '.join([pin(1,'+','passive',0,3.81,270,1.905),pin(2,'-','passive',0,-3.81,90,1.905),pin(3,'MID','passive',-5.08,0,0,2.54)]))
NEW={
 'U8':dict(lib='Stratolink_Power:'+OPNAME,value=OPNAME,fp='Package_TO_SOT_SMD:SOT-23-5',sch=(50.8,190.5),pcb=(55.65,36.1),nets={'1':'SC_BAL_OUT','2':'GND','3':'SC_HALF_REF','4':'SC_BAL_OUT','5':'VBAT'},pins={'1':(7.62,0),'2':(0,-7.62),'3':(-7.62,2.54),'4':(-7.62,-2.54),'5':(0,7.62)},ds='https://www.ti.com/lit/ds/symlink/tlv8801.pdf',mpn='TLV8801DBVT',lcsc='C544879'),
 'R24':dict(lib='Device:R_US',value='4.75MΩ',fp='Resistor_SMD:R_0402_1005Metric',sch=(25.4,184.15),pcb=(57.4,33.9),nets={'1':'VBAT','2':'SC_HALF_REF'},pins={'1':(0,3.81),'2':(0,-3.81)},mpn='FRC0402F4754TS',lcsc='C2998153'),
 'R25':dict(lib='Device:R_US',value='4.75MΩ',fp='Resistor_SMD:R_0402_1005Metric',sch=(25.4,199.39),pcb=(58.65,34.9),nets={'1':'SC_HALF_REF','2':'GND'},pins={'1':(0,3.81),'2':(0,-3.81)},mpn='FRC0402F4754TS',lcsc='C2998153'),
 'R26':dict(lib='Device:R_US',value='22Ω',fp='Resistor_SMD:R_0402_1005Metric',sch=(72.39,190.5),pcb=(61.2,42.5),nets={'1':'SC_BAL_OUT','2':'SC_MID'},pins={'1':(0,3.81),'2':(0,-3.81)},mpn='0402WGF220JTCE',lcsc='C25092'),
 'C22':dict(lib='Device:C',value='100nF',fp='Capacitor_SMD:C_0402_1005Metric',sch=(88.9,190.5),pcb=(55.6,38.3),nets={'1':'VBAT','2':'GND'},pins={'1':(0,3.81),'2':(0,-3.81)},mpn='CL05B104KO5NNNC',lcsc='C1525')}
def label(name,x,y,key):return '(label %s (at %s %s 0) (effects (font (size 0.9 0.9)) (justify left bottom)) (uuid "%s"))'%(json.dumps(name,ensure_ascii=False),x,y,uid(key))
def instance(ref,p,rootid):
 x,y=p['sch'];props=' '.join([prop('Reference',ref,x+1.27 if ref=='U8' else x+4,y-5.08 if ref=='U8' else y-3),prop('Value',p['value'],x if ref=='U8' else x+7,y+17.78 if ref=='U8' else y+1),prop('Footprint',p['fp'],x,y,True),prop('Datasheet',p.get('ds',''),x,y,True),prop('Description','Active midpoint balancer pilot',x,y,True)])
 if p.get('mpn'):props+=' '+prop('MPN',p['mpn'],x,y,True)+' '+prop('LCSC Part #',p['lcsc'],x,y,True)+' '+prop('Supplier Part',p['lcsc'],x,y,True)+' '+prop('Manufacturer_Part_Number',p['mpn'],x,y,True)
 return '(symbol (lib_id "%s") (at %s %s 0) (unit 1) (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no) (uuid "%s") %s %s (instances (project "stratolink" (path "/%s" (reference "%s") (unit 1)))))'%(p['lib'],x,y,uid(ref),props,' '.join('(pin "%s" (uuid "%s"))'%(n,uid(ref+'pin'+n)) for n in p['pins']),rootid,ref)
def change_prop(text,key,value):
 edits=[]
 for s,e,d in prior.spans(text):
  if d==1:
   n=a.parse(text[s:e])
   if n[0]=='property' and n[1]==key:edits.append((s,e,text[s:e].replace(json.dumps(n[2],ensure_ascii=False),json.dumps(value,ensure_ascii=False),1)))
 assert len(edits)==1,(key,len(edits));return prior.replace(text,edits)
def pcb_properties(text,fields):
 n=a.parse(text);x,y=a.one(n,'at')[:2]
 for key,value in fields.items():
  if a.prop(a.parse(text),key) is not None:text=change_prop(text,key,value)
  else:text=text[:-1]+'(property %s %s (at %s %s 0) (layer "B.Fab") (hide yes) (effects (font (size 1 1) (thickness 0.15))))\n)'%(json.dumps(key),json.dumps(value,ensure_ascii=False),x,y)
 return text
def main():
 app=wx.App(False)
 protected={p:sha(p) for p in (ROOT/'hardware/pcb').glob('stratolink.kicad_*') if p.suffix in {'.kicad_pcb','.kicad_sch','.kicad_pro'}}
 names=['stratolink.kicad_pcb','stratolink.kicad_sch','stratolink.kicad_pro','fp-lib-table','sym-lib-table']
 libs=subprocess.check_output(['git','ls-tree','-r','--name-only',BASE+':hardware/pcb/lib'],cwd=ROOT,text=True).splitlines()
 for name in names+['lib/'+n for n in libs]:
  dest=OUT/name;dest.parent.mkdir(parents=True,exist_ok=True);assert not dest.is_symlink();dest.write_bytes(subprocess.check_output(['git','show',BASE+':hardware/pcb/'+name],cwd=ROOT))
 libfile=OUT/'lib/Stratolink_Power.kicad_sym';libfile.write_text('(kicad_symbol_lib (version 20231120) (generator "kicad_symbol_editor")\n'+OP+'\n'+CAP+'\n)\n')
 p=OUT/'sym-lib-table';s=p.read_text();p.write_text(s[:s.rfind(')')]+' (lib (name "Stratolink_Power")(type "KiCad")(uri "${KIPRJMOD}/lib/Stratolink_Power.kicad_sym")(options "")(descr "v1.1 active capacitor balance symbols"))\n)\n')
 p=OUT/'stratolink.kicad_sch';s=p.read_text();rootid=a.scalar(a.parse(s),'uuid');edits=[]
 for st,en,d in prior.spans(s):
  if d!=1:continue
  n=a.parse(s[st:en]);ref=a.prop(n,'Reference') if n[0]=='symbol' else None
  if n[0]=='lib_symbols':
   libsnew=OP.replace('(symbol "'+OPNAME+'"','(symbol "Stratolink_Power:'+OPNAME+'"',1)+'\n'+CAP.replace('(symbol "'+CAPNAME+'"','(symbol "Stratolink_Power:'+CAPNAME+'"',1)
   edits.append((st,en,s[st:en-1]+'\n'+libsnew+'\n)'))
  elif ref=='R1':
   t=change_prop(s[st:en],'Value','7.50MΩ');t=t[:-1]+prop('MPN','FRC0402F7504TS',hide=True)+prop('LCSC Part #','C3013187',hide=True)+prop('Supplier Part','C3013187',hide=True)+prop('Manufacturer_Part_Number','FRC0402F7504TS',hide=True)+')';edits.append((st,en,t))
  elif ref=='C5':
   t=s[st:en].replace('(lib_id "Device:C")','(lib_id "Stratolink_Power:'+CAPNAME+'")',1)
   t=change_prop(t,'Description','Dual-cell supercapacitor; 1 positive, 2 negative, 3 physical midpoint; hand-install')
   t=t[:-1]+'(pin "3" (uuid "%s")))'%uid('C5pin3');edits.append((st,en,t))
 s=prior.replace(s,edits).replace('(paper "User" 265 190)','(paper "User" 265 225)',1)
 added=[label('VBAT',223.52,36.83,'VBAT-existing'),label('SC_MID',228.6,33.02,'mid-existing')]
 for ref,pd in NEW.items():
  added.append(instance(ref,pd,rootid));x,y=pd['sch']
  for num,(px,py) in pd['pins'].items():
   if (ref,num) in [('U8','5'),('U8','2'),('R24','1'),('R25','2'),('R26','2'),('C22','1'),('C22','2')]:added.append(label(pd['nets'][num],round(x+px,4),round(y-py,4),ref+'label'+num))
 wires=[[(25.4,187.96),(43.18,187.96)],[(25.4,187.96),(25.4,195.58)],[(58.42,190.5),(64.77,190.5)],[(64.77,190.5),(64.77,186.69)],[(64.77,186.69),(72.39,186.69)],[(64.77,190.5),(64.77,200.66)],[(64.77,200.66),(39.37,200.66)],[(39.37,200.66),(39.37,193.04)],[(39.37,193.04),(43.18,193.04)]]
 for i,(start,end) in enumerate(wires):added.append('(wire (pts (xy %s %s) (xy %s %s)) (stroke (width 0) (type default)) (uuid "%s"))'%(*start,*end,uid('wire'+str(i))))
 for i,(x,y) in enumerate([(25.4,187.96),(64.77,190.5)]):added.append('(junction (at %s %s) (diameter 0) (color 0 0 0 0) (uuid "%s"))'%(x,y,uid('junction'+str(i))))
 added += [label('SC_HALF_REF',25.4,187.96,'ref-label'),label('SC_BAL_OUT',58.42,190.5,'out-label')]
 added.append('(text "CAP-XX active cell balancing (Fig. 7); hand-install C5 after cleaning.\\nFeedback is before R26. Pilot: verify startup and capacitive-load stability." (at 15 213 0) (effects (font (size 1 1)) (justify left)) (uuid "%s"))'%uid('note'))
 s=s[:s.rfind(')')]+'\n'+'\n'.join(added)+'\n)\n';p.write_text(s)
 # Construct only the new footprints with the native engine; splice those into
 # the original PCB so existing coordinates/metadata are not round-tripped.
 scratch=pcbnew.BOARD();netobjs={}
 for name in sorted({n for pd in NEW.values() for n in pd['nets'].values()}):
  n=pcbnew.NETINFO_ITEM(scratch,boardnet(name));scratch.Add(n);netobjs[name]=n
 share=Path('/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints')
 for ref,pd in NEW.items():
  lib,mod=pd['fp'].split(':');fp=pcbnew.FootprintLoad(str(share/(lib+'.pretty')),mod);assert fp;scratch.Add(fp)
  fp.SetReference(ref);fp.SetValue(pd['value']);fp.SetFPID(pcbnew.LIB_ID(lib,mod));fp.SetPosition(pcbnew.VECTOR2I(0,0));fp.SetPosition(pcbnew.VECTOR2I(*[pcbnew.FromMM(v) for v in pd['pcb']]));fp.Reference().SetVisible(False)
  fp.Flip(fp.GetPosition(),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
  fp.SetOrientationDegrees({'U8':0,'C22':180,'R24':180,'R25':0,'R26':270}[ref])
  
  for pad in fp.Pads():pad.SetNet(netobjs[pd['nets'][pad.GetNumber()]])
 temp=OUT/'new-footprints.kicad_pcb';pcbnew.SaveBoard(str(temp),scratch);newtext=temp.read_text();blocks=[]
 for st,en,d in prior.spans(newtext):
  if d==1:
   n=a.parse(newtext[st:en])
   if n[0]=='footprint':
    ref=a.prop(n,'Reference');t=newtext[st:en];no_silk=[]
    for gs,ge,gd in prior.spans(t):
     if gd==1:
      gn=a.parse(t[gs:ge])
      if gn[0].startswith('fp_') and a.scalar(gn,'layer') in ['F.SilkS','B.SilkS']:no_silk.append((gs,ge,''))
    t=prior.replace(t,no_silk);t=t.replace('(uuid "'+a.scalar(n,'uuid')+'")','(uuid "'+uid('pcb'+ref)+'")',1);t=t[:-1]+'(path "/%s/%s")\n)'%(rootid,uid(ref));pd=NEW[ref];t=pcb_properties(t,{'Description':'Active midpoint balancer pilot','Datasheet':pd.get('ds',''),'MPN':pd['mpn'],'LCSC Part #':pd['lcsc'],'Supplier Part':pd['lcsc'],'Manufacturer_Part_Number':pd['mpn']});blocks.append(t)
 p=OUT/'stratolink.kicad_pcb';s=p.read_text();edits=[]
 for st,en,d in prior.spans(s):
  if d!=1:continue
  n=a.parse(s[st:en]);ref=a.prop(n,'Reference') if n[0]=='footprint' else None
  if n[0]=='segment' and a.scalar(n,'uuid')=='acc183ca-d474-44e8-bd3c-69ef8aaafa23':edits.append((st,en,''))
  elif ref=='R1':edits.append((st,en,pcb_properties(change_prop(s[st:en],'Value','7.50MΩ'),{'MPN':'FRC0402F7504TS','LCSC Part #':'C3013187','Supplier Part':'C3013187','Manufacturer_Part_Number':'FRC0402F7504TS'})))
  elif ref=='C5':
   t=s[st:en];ee=[]
   for ps,pe,pd in prior.spans(t):
    if pd==1:
     pn=a.parse(t[ps:pe])
     if pn[0]=='pad' and pn[1]=='3':assert a.one(pn,'net') is None;ee.append((ps,pe,t[ps:pe-1]+'(net "/SC_MID") (pinfunction "MID") (pintype "passive"))'))
   assert len(ee)==1;t=change_prop(prior.replace(t,ee),'Description','Dual-cell supercapacitor; 1 positive, 2 negative, 3 physical midpoint; hand-install');edits.append((st,en,t))
 s=prior.replace(s,edits).replace('"Net-(U1-VBAT)"','"/VBAT"');s=s[:s.rfind(')')]+'\n'+'\n'.join(blocks)+'\n)\n';p.write_text(s);(OUT.parent/'balancer-unrouted.kicad_pcb').write_text(s)
 assert all(sha(p)==v for p,v in protected.items()),'Canonical files changed during build; inspect concurrent changes.'
 report=dict(status='unrouted-pilot-candidate',baseline=BASE,path=str(OUT),new_parts=NEW,scope=['R1 value8.25M→7.50M; FRC0402F7504TS C3013187 selected','C5 three-terminal symbol and pad3 SC_MID; all pad geometry unchanged','Rename existing Net-(U1-VBAT) net to VBAT without changing connectivity','Add U8,R24,R25,R26,C22 on rear; all existing positions preserved','Schematic paper height190→225mm to fit added circuit','New circuit intentionally unrouted; do not fabricate'],files={n:sha(OUT/n) for n in names+['lib/Stratolink_Power.kicad_sym']})
 (HERE/'balancer-candidate.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
