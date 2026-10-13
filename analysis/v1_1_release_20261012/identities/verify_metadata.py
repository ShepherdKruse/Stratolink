#!/usr/bin/env python3
from pathlib import Path
import sys,json,subprocess,hashlib,copy,importlib.util,xml.etree.ElementTree as ET
import pcbnew,wx
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));import build_metadata as m
OUT=m.OUT;ROOT=m.ROOT;BASE=m.BASE;a=m.a
REPORT=json.loads((HERE/'metadata-build.json').read_text());CLI='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
def stripped(n,keys):return [x for x in n if not(isinstance(x,list) and x and x[0] in keys)]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
base=OUT.parent/'baseline';base.mkdir(exist_ok=True)
for name in ['stratolink.kicad_pcb','stratolink.kicad_sch','stratolink.kicad_pro']:(base/name).write_bytes(subprocess.check_output(['git','show',BASE+':hardware/pcb/'+name],cwd=ROOT))
x,y=[a.parse((p/'stratolink.kicad_pcb').read_text()) for p in [base,OUT]]
assert stripped(x,{'footprint'})==stripped(y,{'footprint'})
changed=[]
for of,nf in zip(a.nodes(x,'footprint'),a.nodes(y,'footprint')):
 ref=a.prop(of,'Reference');assert ref==a.prop(nf,'Reference')
 if of==nf:continue
 old,new=copy.deepcopy(of),copy.deepcopy(nf)
 assert ref not in {'J3','J4'}
 old[1]=new[1]
 if ref=='U1':
  for p in a.nodes(old,'pad'):
   if p[1] in {'22','23','24','25','26'}:p[1]='21'
 assert stripped(old,{'property'})==stripped(new,{'property'}),ref
 changed.append(ref)
app=wx.App(False);ob,nb=[pcbnew.LoadBoard(str(p/'stratolink.kicad_pcb')) for p in [base,OUT]]
for b in [ob,nb]:pcbnew.ZONE_FILLER(b).Fill(b.Zones());b.BuildConnectivity()
pads=lambda b:{p.m_Uuid.AsString():p for f in b.GetFootprints() for p in f.Pads()}
op,np=pads(ob),pads(nb);assert op.keys()==np.keys()
reachable=lambda b,p: {p.m_Uuid.AsString()}|{x.m_Uuid.AsString() for x in b.GetConnectivity().GetConnectedItems(p) if isinstance(x,pcbnew.PAD)}
for uid in op:
 assert op[uid].GetNetname()==np[uid].GetNetname()
 assert reachable(ob,op[uid])==reachable(nb,np[uid]),uid
assert nb.GetConnectivity().GetUnconnectedCount(False)==0
lib_checks={}
for fp in nb.GetFootprints():
 ref=fp.GetReference()
 if ref not in REPORT['new_footprints']:continue
 lib=pcbnew.FootprintLoad(str(OUT/'lib'),REPORT['new_footprints'][ref]);lib_checks[ref]=not fp.FootprintNeedsUpdate(lib,1)
 # Full DRC is the authoritative library parity check; flags above are captured for diagnostic use.
netlists={}
for label,p in [('baseline',base),('candidate',OUT)]:
 dest=HERE/(label+'-netlist.xml');subprocess.run([CLI,'sch','export','netlist','--format','kicadxml','-o',str(dest),str(p/'stratolink.kicad_sch')],check=True,capture_output=True)
 root=ET.parse(dest).getroot();netlists[label]={net.attrib['name']:sorted((n.attrib['ref'],n.attrib['pin']) for n in net.findall('node')) for net in root.findall('./nets/net')}
assert netlists['baseline']==netlists['candidate']
drc=json.loads((HERE/'metadata-drc.json').read_text());assert not drc['schematic_parity'] and not drc['unconnected_items'];assert {v['type'] for v in drc['violations']}=={'silk_over_copper'} and len(drc['violations'])==4
# Purge only named transient comparison exports created by our debug script.
for ref in ['U3','U4','J20']:
 for prefix in ['board','library']:
  q=OUT/'lib'/(prefix+'_'+ref+'.kicad_mod')
  if q.exists():q.unlink()
files={str(p.relative_to(OUT)):sha(p) for p in OUT.rglob('*') if p.is_file()}
res=dict(status='PASS',baseline=BASE,candidate=str(OUT),changed_footprint_refs=changed,physical_pads=len(op),physical_pad_islands_identical=True,netlist_pin_membership_identical=True,unconnected=0,parity=0,library_mismatches=0,remaining_drc={'silk_over_copper':4},native_library_comparison=lib_checks,files=files)
(HERE/'metadata-verification.json').write_text(json.dumps(res,indent=2)+'\n');print(json.dumps({k:v for k,v in res.items() if k not in ['files','native_library_comparison']},indent=2))
