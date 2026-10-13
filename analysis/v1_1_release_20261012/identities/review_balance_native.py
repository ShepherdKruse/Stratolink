#!/usr/bin/env python3
"""Read-only independent circuit and pre-existing pad-island review.

Run with KiCad Python. --candidate must be frozen by its author. Output is new.
This reviews connectivity; it does not establish capacitive-load stability.
"""
from pathlib import Path
import argparse, hashlib, json, subprocess, sys, xml.etree.ElementTree as ET
import pcbnew, wx

parser=argparse.ArgumentParser()
parser.add_argument('--candidate',required=True,type=Path)
parser.add_argument('--baseline',required=True,type=Path)
parser.add_argument('--geometry-baseline',type=Path,help='Optional original authored geometry when the connectivity baseline contains independently revised headers.')
parser.add_argument('--output',required=True,type=Path)
args=parser.parse_args(); out=args.output; out.mkdir(parents=True,exist_ok=False)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
protected={n:sha(args.candidate/n) for n in ['stratolink.kicad_pcb','stratolink.kicad_sch','stratolink.kicad_pro']}
cli='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
r=subprocess.run([cli,'sch','export','netlist','--format','kicadxml','--output',str(out/'netlist.xml'),str(args.candidate/'stratolink.kicad_sch')],capture_output=True,text=True)
(out/'netlist-export.log').write_text(r.stdout+r.stderr); assert r.returncode==0
root=ET.parse(out/'netlist.xml').getroot()
pinmap={}
for net in root.findall('./nets/net'):
 for node in net.findall('node'):pinmap[(node.attrib['ref'],node.attrib['pin'])]=net.attrib['name']
norm=lambda n:n.lstrip('/')
expected={('U8','1'):'SC_BAL_OUT',('U8','2'):'GND',('U8','3'):'SC_HALF_REF',('U8','4'):'SC_BAL_OUT',('U8','5'):'VBAT',('R24','1'):'VBAT',('R24','2'):'SC_HALF_REF',('R25','1'):'SC_HALF_REF',('R25','2'):'GND',('R26','1'):'SC_BAL_OUT',('R26','2'):'SC_MID',('C22','1'):'VBAT',('C22','2'):'GND',('C5','1'):'VBAT',('C5','2'):'GND',('C5','3'):'SC_MID'}
for pair,net in expected.items():assert norm(pinmap[pair])==net,(pair,pinmap.get(pair),net)
values={c.attrib['ref']:c.findtext('value') for c in root.findall('./components/comp')}
for ref,want in [('U8','TLV8801DBVT'),('R1','7.50MΩ'),('R24','4.75MΩ'),('R25','4.75MΩ'),('R26','22Ω'),('C22','100nF')]:assert values[ref]==want,(ref,values[ref],want)
app=wx.App(False); boards=[]
for folder in [args.baseline,args.candidate]:
 b=pcbnew.LoadBoard(str(folder/'stratolink.kicad_pcb'));pcbnew.ZONE_FILLER(b).Fill(b.Zones());b.BuildConnectivity();boards.append(b)
pads=lambda b:{p.m_Uuid.AsString():p for f in b.GetFootprints() for p in f.Pads()}
before,after=map(pads,boards);assert before.keys()<=after.keys()
geometry_folder=args.geometry_baseline or args.baseline
geometry_board=pcbnew.LoadBoard(str(geometry_folder/'stratolink.kicad_pcb'))
geometry_pads=pads(geometry_board);assert geometry_pads.keys()==before.keys()
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'v1_1_solar_attachments_20261012/materials'))
from extract_native import contours
def copper_shapes(p):
 shapes={}
 for layer in [pcbnew.F_Cu,pcbnew.B_Cu]:
  if p.IsOnLayer(layer):
   poly=pcbnew.SHAPE_POLY_SET();p.TransformShapeToPolygon(poly,layer,0,1000,pcbnew.ERROR_OUTSIDE)
   shapes[str(layer)]=contours(poly)
 return shapes
connected=lambda b,p:{p.m_Uuid.AsString()}|{q.m_Uuid.AsString() for q in b.GetConnectivity().GetConnectedItems(p) if isinstance(q,pcbnew.PAD)}
for uid,p in before.items():
 q=after[uid]
 g=geometry_pads[uid]
 assert g.GetPosition()==q.GetPosition() and g.GetDrillSize()==q.GetDrillSize() and copper_shapes(g)==copper_shapes(q),uid
 assert connected(boards[0],p)==connected(boards[1],q)&before.keys(),uid
 # Midpoint becomes intentional SC_MID; existing VBAT only receives a name.
 if p.GetParentFootprint().GetReference()=='C5' and p.GetNumber()=='3':assert norm(q.GetNetname())=='SC_MID'
 elif p.GetNetname()=='Net-(U1-VBAT)':assert norm(q.GetNetname())=='VBAT'
 else:assert p.GetNetname()==q.GetNetname(),(uid,p.GetNetname(),q.GetNetname())
actual={}
for f in boards[1].GetFootprints():
 for p in f.Pads():
  pair=(f.GetReference(),p.GetNumber())
  if pair in expected:actual[pair]=norm(p.GetNetname());assert actual[pair]==expected[pair]
assert actual==expected
assert boards[1].GetConnectivity().GetUnconnectedCount(False)==0
assert protected=={n:sha(args.candidate/n) for n in protected},'Author modified candidate during review.'
result={'status':'PASS','candidate':str(args.candidate),'candidate_sha256':protected,'baseline':str(args.baseline),'baseline_pcb_sha256':sha(args.baseline/'stratolink.kicad_pcb'),'geometry_baseline':str(geometry_folder),'geometry_baseline_pcb_sha256':sha(geometry_folder/'stratolink.kicad_pcb'),'old_pad_count':len(before),'new_pad_count':len(after)-len(before),'existing_physical_pad_islands_preserved':True,'existing_pad_copper_polygons_all_copper_layers_and_drills_preserved':True,'unconnected':0,'feedback_before_22ohm':True,'schematic_and_pcb_expected_pins':{ref+'.'+pin:net for (ref,pin),net in expected.items()},'selected_values':{ref:values[ref] for ref in ['U8','R1','R24','R25','R26','C22']}}
(out/'review.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
