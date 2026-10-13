#!/usr/bin/env python3
"""Freeze placed release footprints and reconcile proven component identities, scratch only."""
from pathlib import Path
import sys,subprocess,json,importlib.util,re,hashlib
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];BASE='59979799c5809d636639084227d9fee75c8de1d9'
OUT=Path.home()/'Repositories/ai-working/scratch/stratolink-release-20261012/identities/metadata-candidate'
spec=importlib.util.spec_from_file_location('prior',ROOT/'analysis/v1_1_ground_20261012/build_candidate.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);a=m.cad
# Exact orderables confirmed in previous JLC order's Selected Parts dialog, not stale project.db.
GROUPS=[('R8','RC0402FR-07100KL','C60491','Yageo'),('FB1','BLM15AG601SN1D','C76884','Murata'),('D1 D3','PESD5V0U1BB','C5272735','Leiditech'),('L1','LPS4018-223MRC','C5278935','Coilcraft'),('L2','PWCWAQ1608F-100KTT','C436784','PROD Tech'),('R10 R18','RC0402FR-0710KL','C60490','Yageo'),('R15 R16','RC0402FR-0733RL','C138002','Yageo'),('C1','GRM1555C1E103JE01D','C3855387','Murata'),('C6','CL21A226MAYNNNE','C602037','Samsung Electro-Mechanics'),('C21 C8','CL10A106KP8NNNC','C19702','Samsung Electro-Mechanics'),('U5','TMP117AIYBGR','C2871893','Texas Instruments'),('U7','LIS2DH12TR','C110926','STMicroelectronics'),('R2','CRCW04024M22FKED','C2091474','Vishay'),('R1 R6','0402WGF8254TCE','C423131','UNI-ROYAL'),('R11 R12','RC0402FR-074K7L','C105871','Yageo'),('C16 C2 C3','CL10A475KP8NNNC','C1705','Samsung Electro-Mechanics'),('U4','MS561101BA03-50','C15639','TE Connectivity'),('C10 C11 C12 C14 C15 C17 C19 C20 C7 C9 C4','CL05B104KO5NNNC','C1525','Samsung Electro-Mechanics'),('U6','LTR-390UV-01','C492374','Lite-On'),('R19 R21 R22 R23','RC0402FR-071ML','C138033','Yageo'),('U1','BQ25570RGRR','C506250','Texas Instruments'),('U3','MAX-M10S-00B','C4153167','u-blox'),('U2','RAK3172-9-SM-NI','C18548052','RAKwireless'),('R5','GR0402F4M42TAG00','C49654874',''),('R3 R7','FRC0402F4754TS','C2998153',''),('R13 R14 R9','RC0402FR-070RL','C106231','Yageo'),('R4','0402WGF3654TCE','C2766827','UNI-ROYAL')]
parts={ref:dict(mpn=mpn,lcsc=lcsc,manufacturer=mf) for refs,mpn,lcsc,mf in GROUPS for ref in refs.split()}
DESCRIPTIONS={'D1':'Bidirectional 5 V low-capacitance ESD TVS, SOD-523; nominal 0.5 pF; PESD5V0U1BB','D3':'Bidirectional 5 V low-capacitance ESD TVS, SOD-523; nominal 0.5 pF; PESD5V0U1BB','U1':'BQ25570 energy-harvesting boost charger and buck converter; RGR VQFN-20 plus exposed ground pad','U2':'RAK3172-9-SM-NI sub-GHz STM32WLE5CC radio module','U3':'MAX-M10S-00B GNSS receiver module','U4':'MS561101BA03-50 digital pressure and temperature sensor','U6':'LTR-390UV-01 ambient light and UVA sensor','U7':'LIS2DH12TR three-axis low-power accelerometer','U5':'TMP117 precision digital temperature sensor, YBG DSBGA-6; max +/-0.2 C at -40 to 100 C, +/-0.25 C at -55 to 125 C under TI test conditions','C5':'DMF4B5R5G105M3DTA0 1 F 5.5 V supercapacitor; CAD pads 1=positive, 2=negative, 3=isolated balance; manual backside assembly'}

def props(text,values,pcb):
 changes=[];found=set();node=a.parse(text);values=dict(values)
 if 'Description' in values:
  for old in a.nodes(node,'property'):
   if old[1] in {'DESCRIPTION','Description_1'}:values[old[1]]=values['Description']
 at=a.one(node,'at') or ['0','0'];x,y=at[:2]
 for s,e,d in m.spans(text):
  if d!=1:continue
  n=a.parse(text[s:e])
  if n[0]=='property' and n[1] in values:
   old='(property '+json.dumps(n[1])+' '+json.dumps(n[2],ensure_ascii=False)
   # Existing escaped unicode representation is not assumed.
   frag=text[s:e];match=re.match(r'\(property\s+"(?:\\.|[^"\\])*"\s+"(?:\\.|[^"\\])*"',frag)
   changes.append((s,e,'(property '+json.dumps(n[1])+' '+json.dumps(values[n[1]],ensure_ascii=False)+frag[match.end():]));found.add(n[1])
 text=m.replace(text,changes)
 for k in values.keys()-found:
  pos='(at 0 0 0) (layer "F.Fab")' if pcb else '(at %s %s 0)'%(x,y)
  text=text[:-1]+'\n (property '+json.dumps(k)+' '+json.dumps(values[k],ensure_ascii=False)+' '+pos+' (effects (font (size 1.27 1.27)) (hide yes)))\n)'
 return text

def main():
 names=['stratolink.kicad_pcb','stratolink.kicad_sch','stratolink.kicad_pro','fp-lib-table','sym-lib-table'];libs=subprocess.check_output(['git','ls-tree','-r','--name-only',BASE+':hardware/pcb/lib'],cwd=ROOT,text=True).splitlines()
 for n in names+['lib/'+n for n in libs]:
  p=OUT/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(subprocess.check_output(['git','show',BASE+':hardware/pcb/'+n],cwd=ROOT))
 drc=json.loads((ROOT/'analysis/v1_1_bare_finish_20261012/review/candidate-drc-project.json').read_text());freeze={v['items'][0]['description'].split()[1] for v in drc['violations'] if v['type']=='lib_footprint_mismatch'}|{'U7'}
 assert not freeze&{'J3','J4'}
 pcb=(OUT/names[0]).read_text();sch=(OUT/names[1]).read_text();pcb_nodes={a.prop(n,'Reference'):n for n in a.nodes(a.parse(pcb),'footprint')};sch_nodes={a.prop(n,'Reference'):n for n in a.nodes(a.parse(sch),'symbol')};fields={};newlibs={}
 for ref in pcb_nodes:
  if ref in {'J3','J4'}:continue
  p=parts.get(ref);v={}
  if p:
   v.update({'Manufacturer_Part_Number':p['mpn'],'LCSC':p['lcsc'],'Supplier Part':p['lcsc'],'Supplier':'LCSC'})
   if p['manufacturer']:v['Manufacturer']=p['manufacturer']
   for existing in a.nodes(sch_nodes.get(ref,[]),'property'):
    if existing[1] in {'MP','Manufacturer Part','MPN','Manufacturer Part Number'}:v[existing[1]]=p['mpn']
   if ref.startswith('U') or ref in {'D1','D3','FB1'}:v['Value']=p['mpn']
   if ref.startswith('R') or ref.startswith('C') or ref=='FB1':v.update({'Datasheet':'https://www.lcsc.com/product-detail/'+p['lcsc']+'.html','Description':p['mpn']})
  if ref in DESCRIPTIONS:v['Description']=DESCRIPTIONS[ref]
  if ref=='U5':v.update({'Value':'TMP117AIYBGR','Manufacturer_Part_Number':'TMP117AIYBGR','MP':'TMP117AIYBGR','Manufacturer':'Texas Instruments','Description_1':DESCRIPTIONS['U5'],'Assembly_Note':'TMP117AIYBGR C2871893: same exact orderable as flown v1; corrected YBG ball map retained. N-grade metadata in earlier CAD was inaccurate.'})
  if ref in {'D1','D3'}:v['Datasheet']='https://uploadcdn.oneyac.com/attachments/files/brand_pdf/leiditech/3D/92/PESD5V0U1BB.pdf'
  if ref=='C5':v.update({'Manufacturer_Part_Number':'DMF4B5R5G105M3DTA0','Manufacturer':'CAP-XX / legacy Murata','Assembly_Note':'Back view: negative left, balance center, positive right. Balance is intentionally unconnected; no pin-order refresh from old library.'})
  if ref in freeze:
   old=pcb_nodes[ref][1];name='Stratolink_v1p1_'+ref+'_'+old.split(':')[-1];v['Footprint']='lib:'+name;newlibs[ref]=name
  if v:fields[ref]=v
 for key,text,pcbmode in [(names[0],pcb,True),(names[1],sch,False)]:
  edits=[]
  for s,e,d in m.spans(text):
   if d!=1:continue
   n=a.parse(text[s:e]);ref=a.prop(n,'Reference') if n[0]==('footprint' if pcbmode else 'symbol') else None
   if ref not in fields:continue
   value=props(text[s:e],fields[ref],pcbmode)
   if pcbmode:
    if ref in newlibs:value=re.sub(r'^\(footprint\s+"[^"\n]+"','(footprint "lib:'+newlibs[ref]+'"',value,count=1)
    if ref=='U1':
     for pin in range(22,27):value=value.replace('(pad "'+str(pin)+'"','(pad "21"',1)
   if not pcbmode and ref=='U5':value=value.replace('(lib_id "TMP117NAIYBGR:TMP117NAIYBGR")','(lib_id "Stratolink_Release:TMP117AIYBGR")')
   if not pcbmode and ref in {'D1','D3'}:value=value.replace('(lib_id "Diode:ESD9B3.3ST5G")','(lib_id "Stratolink_Release:PESD5V0U1BB")')
   edits.append((s,e,value))
  text=m.replace(text,edits)
  if not pcbmode:
   # Preserve original bidirectional TVS geometry and pin electrical semantics, correct identity.
   edits=[];new_symbol=None;tmp_symbol=None
   for s,e,d in m.spans(text):
    if d==2:
     n=a.parse(text[s:e])
     if n[0]=='symbol':
      matched=next((ref for ref,sn in sch_nodes.items() if ref in DESCRIPTIONS and a.scalar(sn,'lib_id')==n[1]),None)
      if matched and matched not in {'D1','D3','U5'}:edits.append((s,e,props(text[s:e],{'Description':DESCRIPTIONS[matched]},False)))
      if n[1]=='TMP117NAIYBGR:TMP117NAIYBGR':
       tmp_symbol=props(text[s:e].replace('TMP117NAIYBGR:TMP117NAIYBGR','Stratolink_Release:TMP117AIYBGR').replace('TMP117NAIYBGR','TMP117AIYBGR'),{'Value':'TMP117AIYBGR','Description':DESCRIPTIONS['U5'],'Description_1':DESCRIPTIONS['U5'],'MP':'TMP117AIYBGR'},False);edits.append((s,e,tmp_symbol))
     if n[:2]==['symbol','Diode:ESD9B3.3ST5G']:
      new_symbol=text[s:e].replace('Diode:ESD9B3.3ST5G','Stratolink_Release:PESD5V0U1BB').replace('ESD9B3.3ST5G','PESD5V0U1BB');new_symbol=props(new_symbol,{'Value':'PESD5V0U1BB','Datasheet':fields['D1']['Datasheet'],'Description':DESCRIPTIONS['D1'],'ki_fp_filters':'*SOD-523*'},False);edits.append((s,e,new_symbol))
   assert new_symbol and tmp_symbol;text=m.replace(text,edits)
   (OUT/'lib/Stratolink_Release.kicad_sym').write_text('(kicad_symbol_lib (version 20250114) (generator "kicad_symbol_editor")\n'+new_symbol.replace('"Stratolink_Release:PESD5V0U1BB"','"PESD5V0U1BB"',1)+'\n'+tmp_symbol.replace('"Stratolink_Release:TMP117AIYBGR"','"TMP117AIYBGR"',1)+'\n)\n')
  (OUT/key).write_text(text)
 table=(OUT/'sym-lib-table').read_text();(OUT/'sym-lib-table').write_text(table.rstrip()[:-1]+' (lib (name "Stratolink_Release")(type "KiCad")(uri "${KIPRJMOD}/lib/Stratolink_Release.kicad_sym")(options "")(descr "Verified v1.1 component identity"))\n)\n')
 (HERE/'metadata-build.json').write_text(json.dumps(dict(baseline=BASE,candidate=str(OUT),fields=fields,new_footprints=newlibs,thermal_pad_renumber={'22':'21','23':'21','24':'21','25':'21','26':'21'}),indent=2)+'\n')
 print('Built',OUT,'footprint variants',len(newlibs),'metadata refs',len(fields))
if __name__=='__main__':main()
