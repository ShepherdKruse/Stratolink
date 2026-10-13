"""Scratch-only AS7331 ECO, deterministic geometry; run bundled KiCad Python."""
from pathlib import Path
import importlib.util,sys,shutil,json,uuid,re,hashlib,subprocess,copy
import pcbnew,wx
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];SRC=ROOT/'hardware/pcb';OUT=Path.home()/'Repositories/ai-working/scratch/stratolink-release-20261012/as7331/candidate'
spec=importlib.util.spec_from_file_location('m',HERE.parents[1]/'identities/build_metadata.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);a=m.a;spans=m.m.spans;replace=m.m.replace
NS=uuid.UUID('10d9e102-2cba-493c-a14b-cf184fb8d8b7')
def uid(k):return str(uuid.uuid5(NS,k))
def q(s):return json.dumps(s,ensure_ascii=False)
def direct(text,kind):return [(s,e,text[s:e],a.parse(text[s:e])) for s,e,d in spans(text) if d==1 and text[s:e].split(None,1)[0]=='('+kind]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
FP='Stratolink_v1p1_U6_AS7331_OLGA16';DS='https://look.ams-osram.com/m/1856fd2c69c35605/original/AS7331-Spectral-UVA-B-C-Sensor.pdf'
PINNAMES={str(i):('VSSA' if i in [1,2,5,6,15,16] else {3:'VDDA',4:'REXT',7:'A1',8:'SYN',9:'READY',10:'VDDD',11:'VSSD',12:'SDA',13:'SCL',14:'A0'}[i]) for i in range(1,17)}
NETS={str(i):('GND' if i in [1,2,5,6,7,8,11,14,15,16] else {3:'+3.3V',4:'/UV_REXT',9:'unconnected-(U6-READY-Pad9)',10:'+3.3V',12:'SDA',13:'SCL'}[i]) for i in range(1,17)}
TYPES={i:('power_in' if n in ['VSSA','VSSD','VDDA','VDDD'] else 'output' if n=='READY' else 'bidirectional' if n=='SDA' else 'passive' if n=='REXT' else 'input') for i,n in PINNAMES.items()}
POS={**{str(i+1):(-.75+.5*i,-1.575) for i in range(4)},**{str(i+5):(1.05,-.75+.5*i) for i in range(4)},**{str(12-i):(-.75+.5*i,1.575) for i in range(4)},**{str(16-i):(-1.05,-.75+.5*i) for i in range(4)}}
PLACEMENT={'U6':(74.25,37.1,0),'C14':(74.3,34.5,0),'C23':(75.2,39.8,0),'R27':(71.9,34.08,90),'C21':(69.362,34.647,180)}
FIELDS={'U6':{'Value':'AS7331-AQFM','Manufacturer':'ams OSRAM','Manufacturer_Part_Number':'AS7331-AQFM','LCSC':'C20482877','Supplier Part':'C20482877','Supplier':'LCSC','Datasheet':DS,'Description':'UVA UVB UVC spectral sensor; 0x74, CMD mode, READY NC, -40 to 85 C; ozone research requires calibrated optics','Footprint':'lib:'+FP},'R27':{'Value':'3.3MΩ','Manufacturer':'Vishay','Manufacturer_Part_Number':'MCU0805MD3304BP500','LCSC':'C4313228','LCSC Part #':'C4313228','Supplier Part':'C4313228','Supplier':'LCSC','Datasheet':'https://www.vishay.com/docs/28952/mcr0201at-mca1206at.pdf','Description':'3.3 MΩ, ±0.1%, ±25 ppm/K, 0805 precision thin film; AS7331 reference','Footprint':'lib:Stratolink_v1p1_R27_R_0805_2012Metric'},'C23':{'Value':'100nF','Manufacturer':'Samsung Electro-Mechanics','Manufacturer_Part_Number':'CL05B104KO5NNNC','LCSC':'C1525','Supplier Part':'C1525','Supplier':'LCSC','Datasheet':'https://www.lcsc.com/product-detail/C1525.html','Description':'AS7331 VDDD local bypass, 100 nF 0402','Footprint':'lib:Stratolink_v1p1_C23_C_0402_1005Metric'}}
def prop(n,v,x=0,y=0,hide=True):return f'(property {q(n)} {q(v)} (at {x} {y} 0) (effects (font (size 1 1)){" (hide yes)" if hide else ""}))'
def libsymbol():
 parts=[prop('Reference','U',0,12.7,False),prop('Value','AS7331-AQFM',0,-12.7,False),*[prop(k,v) for k,v in FIELDS['U6'].items() if k!='Value']]
 graphics='(rectangle (start -10.16 11.43) (end 10.16 -11.43) (stroke (width .254) (type default)) (fill (type background)))'
 pins=[]
 for nums,x,rot in [([12,13,8,7,14,4,3,10],-12.7,0),([9,1,2,5,6,15,16,11],12.7,180)]:
  for k,num in enumerate(nums):
   n=str(num);y=10.16-k*2.54;pins.append(f'(pin {TYPES[n]} line (at {x} {y} {rot}) (length 2.54) (name {q(PINNAMES[n])} (effects (font (size 1 1)))) (number {q(n)} (effects (font (size 1 1)))))')
 return '(symbol "AS7331_AQFM" (pin_names (offset .5)) (exclude_from_sim no) (in_bom yes) (on_board yes) '+' '.join(parts)+' (symbol "AS7331_AQFM_0_1" '+graphics+') (symbol "AS7331_AQFM_1_1" '+' '.join(pins)+'))'
def label(net,x,y,key):
 if net in ['SDA','SCL']:return f'(global_label {q(net)} (shape bidirectional) (at {x} {y} 180) (effects (font (size .9 .9)) (justify right)) (uuid {q(uid(key))}))'
 if net=='GND':return f'(label "GND" (at {x} {y} 0) (effects (font (size .9 .9)) (justify left bottom)) (uuid {q(uid(key))}))'
 if net.startswith('/'):return f'(label {q(net[1:])} (at {x} {y} 0) (effects (font (size .9 .9)) (justify left bottom)) (uuid {q(uid(key))}))'
 return f'(label {q(net)} (at {x} {y} 0) (effects (font (size .9 .9)) (justify left)) (uuid {q(uid(key))}))'
def move_symbol(block,ref,pos,fields,newid=None):
 n=a.parse(block);old=a.floats(n,'at');ed=[]
 for s,e,d in spans(block):
  nn=a.parse(block[s:e])
  if nn[0]=='at' and (d==1 or d==2):
   at=list(map(float,nn[1:]));at[0]+=pos[0]-old[0];at[1]+=pos[1]-old[1];ed.append((s,e,'(at '+' '.join(str(v) for v in at)+')'))
 block=replace(block,ed);block=m.props(block,{'Reference':ref,**fields},False)
 if newid:
  block=block.replace(a.scalar(n,'uuid'),newid)
  for pin in a.nodes(n,'pin'):block=block.replace(a.scalar(pin,'uuid'),uid(ref+'pin'+pin[1]))
  oldref=a.prop(n,'Reference');block=block.replace('(reference '+q(oldref)+')','(reference '+q(ref)+')')
 return block

def main():
 app=wx.App(False)
 manifest=json.loads((ROOT/'hardware/gerbers/v1.1-pilot/manifest.json').read_text());protected=manifest['source_files'];assert all(sha(SRC/n)==h for n,h in protected.items())
 if OUT.exists():shutil.rmtree(OUT)
 for n in protected:
  d=OUT/n;d.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(SRC/n,d)
 (HERE/'baseline-source-hashes.json').write_text(json.dumps(protected,indent=2)+'\n')
 sch=(OUT/'stratolink.kicad_sch').read_text();nodes={a.prop(n,'Reference'):(s,e,t,n) for s,e,t,n in direct(sch,'symbol')};rootid=a.scalar(a.parse(sch),'uuid');u6id=a.scalar(nodes['U6'][3],'uuid')
 sym=libsymbol();(OUT/'lib/Stratolink_UV.kicad_sym').write_text('(kicad_symbol_lib (version 20250114) (generator "kicad_symbol_editor")\n'+sym+'\n)\n')
 table=OUT/'sym-lib-table';table.write_text(table.read_text().rstrip()[:-1]+' (lib (name "Stratolink_UV")(type "KiCad")(uri "${KIPRJMOD}/lib/Stratolink_UV.kicad_sym")(options "")(descr "AS7331 datasheet-v4-00 verified symbol"))\n)\n')
 ed=[]
 for s,e,t,n in direct(sch,'lib_symbols'):ed.append((s,e,t[:-1]+sym.replace('(symbol "AS7331_AQFM"','(symbol "Stratolink_UV:AS7331_AQFM"',1)+')'))
 # Retire only old U6/C14 wires and labels; preserve C16 power cluster.
 deleted=[]
 for s,e,d in spans(sch):
  if d!=1:continue
  n=a.parse(sch[s:e]);remove=False;ref=a.prop(n,'Reference')
  if n[0]=='symbol' and ref in ['U6','C14']:remove=True
  if n[0]=='wire':
   p=[[float(v) for v in xy[1:]] for xy in a.nodes(a.one(n,'pts'),'xy')]
   if all(27.94<=x<=68 and 125<y<141 for x,y in p) and max(x for x,y in p)>27.94:remove=True
  if n[0] in ['junction','global_label','no_connect','text']:
   at=a.floats(n,'at')
   if at and 32<at[0]<80 and 125<at[1]<141:remove=True
  if remove:ed.append((s,e,''));deleted.append(a.scalar(n,'uuid'))
 sch=replace(sch,ed)
 # Lift the preserved C16 supply cluster one grid step for legible UV notes.
 lifted=[]
 for ss,ee,dd in spans(sch):
  if dd!=1:continue
  block=sch[ss:ee];nn=a.parse(block);at=a.floats(nn,'at')
  if nn[0]=='symbol' and at and abs(at[0]-27.94)<.001 and 125<at[1]<142:
   lifted.append((ss,ee,move_symbol(block,a.prop(nn,'Reference'),(at[0],at[1]-2.54),{})))
  elif nn[0]=='wire':
   pts=a.nodes(a.one(nn,'pts'),'xy')
   if pts and all(abs(float(xy[1])-27.94)<.001 and 125<float(xy[2])<142 for xy in pts):
    lifted.append((ss,ee,re.sub(r'\(xy ([^ ]+) ([^)]+)\)',lambda mat:'(xy '+mat[1]+' '+str(float(mat[2])-2.54)+')',block)))
  elif nn[0]=='junction' and at and abs(at[0]-27.94)<.001 and 125<at[1]<142:
   lifted.append((ss,ee,re.sub(r'\(at [^)]+\)',f'(at {at[0]} {at[1]-2.54})',block,count=1)))
 sch=replace(sch,lifted)
 # Expand existing UV section box upward into previously empty schematic area.
 sch=sch.replace('(start 13.97 123.19)', '(start 13.97 88.90)')
 sx,sy=50.8,107.95;add=[];pinloc={}
 for nums,x in [([12,13,8,7,14,4,3,10],-12.7),([9,1,2,5,6,15,16,11],12.7)]:
  for k,num in enumerate(nums):pinloc[str(num)]=(sx+x,sy-(10.16-k*2.54))
 properties=' '.join([prop('Reference','U6',sx,sy-14,False),*[prop(k,v,sx,sy+14 if k=='Value' else sy,k!='Value') for k,v in FIELDS['U6'].items()]])
 add.append(f'(symbol (lib_id "Stratolink_UV:AS7331_AQFM") (at {sx} {sy} 0) (unit 1) (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no) (uuid {q(u6id)}) {properties} '+''.join(f'(pin {q(i)} (uuid {q(uid("U6pin"+i))}))' for i in PINNAMES)+f'(instances (project "stratolink" (path "/{rootid}" (reference "U6") (unit 1)))))')
 for n,(x,y) in pinloc.items():
  if n=='9':add.append(f'(no_connect (at {x} {y}) (uuid {q(uid("NC9"))}))');continue
  left=x<sx;xx=x+(-5.08 if left else 2.54)
  add.append(f'(wire (pts (xy {x} {y}) (xy {xx} {y})) (stroke (width 0) (type default)) (uuid {q(uid("stub"+n))}))')
  lab=label(NETS[n],xx,y,'labelU6'+n)
  if left and NETS[n] not in ['SDA','SCL']:
   if True:lab=lab.replace('(justify left bottom)','(justify right bottom)').replace('(justify left)','(justify right bottom)')
   else:lab=lab.replace(f'(at {xx} {y} 0)',f'(at {xx} {y} 180)')
  add.append(lab)
 c14=move_symbol(nodes['C14'][2],'C14',(40.64,130.81),{'Description':'AS7331 VDDA local bypass, 100 nF 0402'})
 c23=move_symbol(nodes['C14'][2],'C23',(55.88,130.81),FIELDS['C23'],uid('C23'))
 r27=move_symbol(nodes['R26'][2],'R27',(68.58,130.81),{**FIELDS['R27'],'MPN':'MCU0805MD3304BP500'},uid('R27'))
 r27=replace(r27,[(ss,ee,re.sub(r'\(at [^)]+\)', '(at 68.58 137.16 0)',tt,count=1)) for ss,ee,tt,nn in direct(r27,'property') if nn[1]=='Value'])
 def show_ref(block,x):
  return replace(block,[(ss,ee,re.sub(r'\(at [^)]+\)', f'(at {x} 137.16 0)',tt.replace('(hide yes)',''),count=1)) for ss,ee,tt,nn in direct(block,'property') if nn[1]=='Reference'])
 c14=show_ref(c14,40.64);c23=show_ref(c23,55.88)
 add.extend([c14,c23,r27])
 for ref,x in [('C14',40.64),('C23',55.88)]:add.extend([label('+3.3V',x,127.0,ref+'v'),label('GND',x,134.62,ref+'g')])
 # R26 template orientation0 pin1above,pin2below.
 add.extend([label('/UV_REXT',68.58,127.0,'rref'),label('GND',68.58,134.62,'rgnd')])
 add.append('(text "AS7331: 0x74, polled CMD, SYN=GND, READY unconnected.\\nR27: 3.3 MΩ ±0.1%, 25 ppm/K. C14/C23: local analog/digital bypass.\\nExperimental UV channels; ozone column needs calibrated optics." (at 15.24 142.5 0) (effects (font (size .85 .85)) (justify left)) (uuid '+q(uid('note'))+'))')
 (OUT/'stratolink.kicad_sch').write_text(sch.rstrip()[:-1]+'\n'+'\n'.join(add)+'\n)\n')
 pro=OUT/'stratolink.kicad_pro';j=json.loads(pro.read_text());j['erc']['erc_exclusions']=[v for v in j['erc']['erc_exclusions'] if 'LTR-390UV' not in v[1]];pro.write_text(json.dumps(j,indent=2)+'\n')
 dru=OUT/'stratolink.kicad_dru';dru.write_text(dru.read_text().split('# U7 MEMS escape passes U6')[0]+'\n(rule "U6 AS7331 fine pitch lands" (condition "A.Type == \'Pad\' && B.Type == \'Pad\' && A.memberOfFootprint(\'U6\') && B.memberOfFootprint(\'U6\')") (constraint clearance (min 0.15mm)))\n')
 # Generate component-local footprint model; 0.35 lands derived from max terminal,
 # NOT represented as a manufacturer-recommended land pattern.
 fp='(footprint '+q(FP)+' (version 20241229) (generator "pcbnew") (layer "F.Cu") (attr smd) (descr "AS7331 OLGA16 top-view map from DS001047 v4-00 Fig59; derived 0.35 mm lands, 0.30 mm paste") (property "Reference" "U6" (at 0 -2.5 0) (layer "F.Fab") (effects (font (size .8 .8)))) (property "Value" "AS7331-AQFM" (at 0 2.5 0) (layer "F.Fab") (hide yes) (effects (font (size .8 .8)))) (solder_paste_margin -0.025)'
 for layer,bounds,width in [('F.Fab',(-1.3,-1.825,1.3,1.825),.1),('F.CrtYd',(-1.5,-2.025,1.5,2.025),.05)]:
  x0,y0,x1,y1=bounds
  fp+=f'(fp_rect (start {x0} {y0}) (end {x1} {y1}) (stroke (width {width}) (type default)) (fill none) (layer "{layer}"))'
 fp+='(fp_circle (center -.95 -1.45) (end -.85 -1.45) (stroke (width .1) (type default)) (fill none) (layer "F.Fab"))'
 fp+='(fp_rect (start -.475 -.475) (end .475 .475) (stroke (width .05) (type default)) (fill none) (layer "F.Fab"))'
 for n,(x,y) in POS.items():fp+=f'(pad {q(n)} smd rect (at {x} {y}) (size .35 .35) (layers "F.Cu" "F.Paste" "F.Mask") (zone_connect 2))'
 fp+='(model "${KIPRJMOD}/3d/AS7331_OLGA16.wrl" (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))\n)\n';(OUT/'lib'/f'{FP}.kicad_mod').write_text(fp)
 # Native footprint instancing preserves IDs of every retained part.
 b=pcbnew.LoadBoard(str(OUT/'stratolink.kicad_pcb'));baseline_tracks={t.m_Uuid.AsString():t.GetNetname() for t in b.GetTracks()};by={f.GetReference():f for f in b.GetFootprints()};old=by['U6'];oldpath=old.GetPath();olduuid=old.m_Uuid.AsString();b.Remove(old);uuidmap={}
 for net in ['/UV_REXT','unconnected-(U6-READY-Pad9)']:
  if net not in b.GetNetsByName():b.Add(pcbnew.NETINFO_ITEM(b,net))
 f=pcbnew.FootprintLoad(str(OUT/'lib'),FP);b.Add(f);f.SetReference('U6');f.SetPath(oldpath);f.SetFPID(pcbnew.LIB_ID('lib',FP));uuidmap[f.m_Uuid.AsString()]=olduuid
 for p in f.Pads():p.SetNet(b.GetNetsByName()[NETS[p.GetNumber()]]);p.SetPinFunction(PINNAMES[p.GetNumber()]);p.SetPinType(TYPES[p.GetNumber()])
 by['U6']=f
 for ref,template,schid in [('C23','C14',uid('C23')),('R27',None,uid('R27'))]:
  if template:f=pcbnew.FootprintLoad(str(OUT/'lib'),'Stratolink_v1p1_C14_C_0402_1005Metric')
  else:f=pcbnew.FootprintLoad('/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints/Resistor_SMD.pretty','R_0805_2012Metric')
  b.Add(f);f.SetReference(ref);uuidmap[f.m_Uuid.AsString()]=uid('pcb'+ref);f.SetPath(pcbnew.KIID_PATH('/'+rootid+'/'+schid));f.SetFPID(pcbnew.LIB_ID('lib',FIELDS[ref]['Footprint'].split(':')[1]));by[ref]=f
  for p in f.Pads():p.SetNet(b.GetNetsByName()[('GND' if p.GetNumber()=='1' else '+3.3V') if ref=='C23' else ('/UV_REXT' if p.GetNumber()=='1' else 'GND')]);p.SetPinFunction('');p.SetPinType('passive')
 for ref,(x,y,ang) in PLACEMENT.items():
  f=by[ref];f.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x),pcbnew.FromMM(y)));f.SetOrientationDegrees(ang);f.Reference().SetVisible(False)
  if ref in FIELDS:
   for k,v in FIELDS[ref].items():
    if k=='Value':f.SetValue(v)
    elif k!='Footprint':pass
 for ref in ['C14','C16']:
  for pad in by[ref].Pads():
   if pad.GetNetname()=='GND':pad.SetThermalSpokeAngleDegrees(45)
 for g in list(by['R27'].GraphicalItems()):
  if g.GetLayer()==pcbnew.F_SilkS:by['R27'].Remove(g)
 # Remove the old component-only +3.3/GND branches and SDA/SCL terminal stubs.
 remove={'6086e0aa-4b6c-4c59-9965-ed9f1305fd15','6d3ebafd-c40f-478b-b1d8-9dfbb1ff9320','8b6f8cf1-5e09-4e27-859e-0e61ba76ec99','943999be-a8ef-41fc-843e-78b4b5483bc4','b89cf478-d723-4674-9bad-b1c68747730a','dd2efa30-4487-44ed-b855-e9480d9de7c6','e205f7e4-bc4b-40ec-99df-1381e0a67a56','72597cd9-b8fe-4299-bb42-ed8d20f938e1','82cfbabc-eb6d-4eb3-a547-158b1a5088aa','d8327169-7241-4e9d-bf3f-c18dbe25c5c8','61e93a13-911b-43d1-ae98-6217c3621b91','811e789f-a324-46da-a947-e6dc8e8e012b'}
 remove.update({'d1f5d95e-4f63-5197-a83a-6543d22cd26d','73e7f9cb-7cde-4790-99d5-39f0210b1718','5279d3eb-a2a4-4a5b-8873-c7b27e48c3db','ba200d33-b863-4501-a1e2-84e570cb3a30','c2b71d8f-6204-446b-8d9a-9471fe1a2e01','4bde1a70-cc6c-4f9e-95a2-a838219fcb08','2c73519c-5d85-4fb6-94f2-fdf4fd090a19','8f2d3059-79ff-4bed-bbc8-97b8c2e96284','63ae4665-b2db-47a6-9df8-d624d874c027','084f312f-8a73-5cac-86e3-9e2201dbe674','85d21f9a-d306-4d93-aa30-e021dec87b0c','3d757bd2-62fc-4648-ac00-999f10e529d0','3dae8f90-54db-4d1d-9013-f918fe9f2193','3e2fa8dc-838c-465f-898f-f5a7814705f7','b0af08ff-5937-48a2-8855-60dd3fc032cd','f5e25bf7-0cc0-4f44-aa17-b38b27c40598','e84241fc-26ee-4b9e-a7f2-2ae95117bb37','136d03c2-7ad1-54b5-8bb1-f975625793c3','5249d9d1-febc-43bf-af94-1ecc52d804a8','67036e15-6d22-4300-8970-be44f0bef612','ab156f57-4a24-46fa-a756-3fca6b2c27c6','c6a072d2-8ea5-4450-a116-37ac904d32d8','eb0b7306-f0ab-4251-8bfb-1da50641f8b7','f748967a-ba3d-44a6-b9f7-a097f547390e','339a9c02-a791-4125-8f41-b9338896d6b4','7a4c3dcd-6733-4642-a144-2e8bb6cbb508','802253f4-7df1-4bb6-b466-43befbc705b7','d4261336-4894-4f18-99ce-27ebe85aff42','0642127c-ad0f-43bb-b30f-724321f0f20a','caf799d7-9d5c-43ce-bcef-2f15b4987fe9','d31635cf-39a9-4a48-b446-a652a41511d0','e2350b39-6d24-40d6-8255-7aee59ac70be','fd1079ac-d644-4b39-b5e0-f898d81efe99','7c78c218-96bc-4aca-b074-6f44a85d0fb1','abc32322-38b2-4052-83c4-1a9093e9507b','8b6ba619-85cc-4b9e-8cbe-dcff90c1bcc4','97ec6c48-d347-4605-9ed9-c0da0ebad43a','09531328-a751-451d-9335-f02886d92d81','0f6230f4-b7ae-4de6-a0f7-88e948a7461d','17a79630-fe0f-4599-8fa4-729f6ab0ed5c','d5f4b07c-7b6d-4573-b9c3-58bb918f0da1','140fa833-2dfb-4a51-b614-4ce85f4ff836'})
 for t in list(b.GetTracks()):
  if t.m_Uuid.AsString() in remove:b.Remove(t)
  elif t.m_Uuid.AsString()=='d1f5d95e-4f63-5197-a83a-6543d22cd26d':t.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(70.7),pcbnew.FromMM(40.6)))
  elif t.m_Uuid.AsString()=='084f312f-8a73-5cac-86e3-9e2201dbe674':t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(71.4),pcbnew.FromMM(39.0)))
  elif t.m_Uuid.AsString()=='d77de296-cfdd-4a11-9366-786834a091e5':t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(70.137),pcbnew.FromMM(34.647)))
  elif t.m_Uuid.AsString()=='cbeea82c-ea8a-409b-ac8d-3d69958a2bb4':t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(75.909911),pcbnew.FromMM(43.0)))
  elif t.m_Uuid.AsString()=='1479ae7e-ebb6-4769-ac24-dc46d3e4bcaa':t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(70.8),pcbnew.FromMM(33.503)))
  elif t.m_Uuid.AsString()=='ae48f841-4920-4bf3-be99-e887d838269a':t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(75.452),pcbnew.FromMM(41.8)))
  elif t.GetLayer()==pcbnew.F_Cu and t.GetNetname()=='SDA' and abs(pcbnew.ToMM(t.GetStart().x)-75.038)<.01 and abs(pcbnew.ToMM(t.GetStart().y)-40.106)<.01:t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(75.038),pcbnew.FromMM(41.8)))
 pcbnew.SaveBoard(str(OUT/'stratolink.kicad_pcb'),b)
 p=OUT/'stratolink.kicad_pcb';t=p.read_text()
 for oldid,newid in uuidmap.items():t=t.replace(oldid,newid)
 t=replace(t,[(s,e,m.props(block,{k:v for k,v in ({**FIELDS.get(a.prop(n,'Reference'),{}),**({'Description':'AS7331 VDDA local bypass, 100 nF 0402'} if a.prop(n,'Reference')=='C14' else {}),**({'MPN':'MCU0805MD3304BP500'} if a.prop(n,'Reference')=='R27' else {})}).items() if k!='Footprint'},True)) for s,e,block,n in direct(t,'footprint') if a.prop(n,'Reference') in FIELDS or a.prop(n,'Reference')=='C14'])
 ed=[]
 for ss,ee,block,nn in direct(t,'segment')+direct(t,'via'):
  ident=a.scalar(nn,'uuid')
  if ident in baseline_tracks and a.scalar(nn,'net')!=baseline_tracks[ident]:
   block=re.sub(r'\(net "[^"]*"\)', '(net '+q(baseline_tracks[ident])+')',block);ed.append((ss,ee,block))
 t=replace(t,ed)
 # Freeze the standard resistor model inside this project, like all retained components.
 modelsrc=Path('/Applications/KiCad/KiCad.app/Contents/SharedSupport/3dmodels/Resistor_SMD.3dshapes/R_0805_2012Metric.step')
 shutil.copyfile(modelsrc,OUT/'3d/R_0805_2012Metric.step')
 t=replace(t,[(ss,ee,re.sub(r'\(model \"[^\"]+\"', '(model \"${KIPRJMOD}/3d/R_0805_2012Metric.step\"',block)) for ss,ee,block,nn in direct(t,'footprint') if a.prop(nn,'Reference')=='R27'])
 p.write_text(t)
 # Freeze local copper/body geometry in a separate native-engine process.
 subprocess.run([sys.executable,str(HERE/'freeze_new.py'),str(OUT)],check=True)
 # Small source-generated VRML, mm converted to legacy KiCad0.1inch units.
 def box(name,size,center,color):
  scale=1/2.54;sz=' '.join(str(v*scale) for v in size);ct=' '.join(str(v*scale) for v in center)
  return f'# {name}\nTransform {{ translation {ct} children [ Shape {{ appearance Appearance {{ material Material {{ diffuseColor {color} }} }} geometry Box {{ size {sz} }} }} ] }}\n'
 model='#VRML V2.0 utf8\n# Nominal manufacturer outline; visualization, no mass or optical performance claim.\n'
 model+=box('OLGA substrate',(2.6,3.65,.1),(0,0,.05),'.08 .22 .08')+box('body',(2.6,3.65,.99),(0,0,.595),'.17 .17 .2')+box('aperture .950 square',(.95,.95,.01),(0,0,1.095),'.22 .30 .32')+box('pin1 top-left marker',(.15,.15,.012),(-1.00,1.50,1.096),'.82 .82 .82')
 for n,(x,y) in POS.items():model+=box('terminal'+n,(.3,.3,.015),(x,-y,.005),'.75 .68 .4')
 (OUT/'3d/AS7331_OLGA16.wrl').write_text(model)
 assert all(sha(SRC/n)==h for n,h in protected.items())
 (HERE/('build.json' if OUT.name=='candidate' else 'build-'+OUT.name+'.json')).write_text(json.dumps(dict(candidate=str(OUT),source_hashes=protected,placement=PLACEMENT,pins=PINNAMES,nets=NETS,terminal_centers_mm=POS,lands_mm=[.35,.35],paste_mm=[.30,.30],removed_tracks=sorted(remove),removed_schematic=deleted,scope='Unrouted candidate; not for fabrication'),indent=2)+'\n')
 print(OUT)
if __name__=='__main__':
 if len(sys.argv)>1:
  requested=Path(sys.argv[1]).resolve();assert requested.parent==OUT.parent
  OUT=requested
 main()
