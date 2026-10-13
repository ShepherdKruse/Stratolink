#!/usr/bin/env python3
"""Read native KiCad STEP/GLB exports and screen balancer assembly envelopes.

Run with the existing OCCT environment. Exports are created separately by KiCad;
--exports contains <ref>-board.step and J1.glb/J2.glb. Source geometry is untouched.
"""
from pathlib import Path
import argparse,json,struct,math,hashlib
from OCP.STEPControl import STEPControl_Reader
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.TopAbs import TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
parser=argparse.ArgumentParser();parser.add_argument('--exports',required=True,type=Path);parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
def bounds(shape):
 b=Bnd_Box();BRepBndLib.AddOptimal_s(shape,b);mn=b.CornerMin();mx=b.CornerMax()
 return [[mn.X(),mn.Y(),mn.Z()],[mx.X(),mx.Y(),mx.Z()]]
def union(boxes):return [[min(b[0][i] for b in boxes) for i in range(3)],[max(b[1][i] for b in boxes) for i in range(3)]]
def gap(a,b):return math.sqrt(sum(max(0,a[0][i]-b[1][i],b[0][i]-a[1][i])**2 for i in range(3)))
parts={};records={};files={};newrefs=['U8','R24','R25','R26','C22']
neighbors=[ref for ref in ['L1','D3','U3','AE2'] if (args.exports/(ref+'-board.step')).exists()]
for ref in ['C5']+newrefs+neighbors:
 p=args.exports/(ref+'-board.step');files[p.name]=hashlib.sha256(p.read_bytes()).hexdigest();r=STEPControl_Reader();r.ReadFile(str(p));assert r.TransferRoots()>0
 e=TopExp_Explorer(r.OneShape(),TopAbs_SOLID);solids=[];boxes=[];removed=0
 while e.More():
  s=e.Current();b=bounds(s)
  if b[1][0]-b[0][0]>20 and b[1][1]-b[0][1]>50 and b[1][2]-b[0][2]<.5:removed+=1
  else:
   assert BRepCheck_Analyzer(s).IsValid(),ref
   solids.append(s);boxes.append(b)
  e.Next()
 assert solids and removed==1,(ref,len(solids),removed)
 parts[ref]=solids;records[ref]={'solid_count':len(solids),'bounds_mm':union(boxes),'individual_solid_bounds_mm':boxes,'valid_brep':True}
for ref in newrefs:
 distances=[]
 for a in parts[ref]:
  for b in parts['C5']:
   d=BRepExtrema_DistShapeShape(a,b);d.Perform();assert d.IsDone();distances.append(d.Value())
 records[ref]['nominal_distance_to_C5_mm']=min(distances);assert min(distances)>0
 adjacent={}
 for other in newrefs+neighbors:
  if other==ref:continue
  ds=[]
  for a in parts[ref]:
   for b in parts[other]:
    d=BRepExtrema_DistShapeShape(a,b);d.Perform();assert d.IsDone();ds.append(d.Value())
  adjacent[other]=min(ds);assert min(ds)>0,(ref,other,min(ds))
 records[ref]['nominal_distance_to_nearby_models_mm']=adjacent
 # H1 has a 2 mm hole at (55.665,31.745), in board coordinates.
 b=records[ref]['bounds_mm'];dx=max(b[0][0]-55.665,55.665-b[1][0],0);dy=max(b[0][1]+31.745,-31.745-b[1][1],0)
 records[ref]['H1_hole_to_model_xy_bbox_lower_bound_mm']=math.hypot(dx,dy)-1.0
solar={}
for ref in ['J1','J2']:
 p=args.exports/(ref+'.glb');data=p.read_bytes();files[p.name]=hashlib.sha256(data).hexdigest();n,t=struct.unpack_from('<II',data,12);assert t==0x4E4F534A;j=json.loads(data[20:20+n]);node=next(n for n in j['nodes'] if n.get('name')==ref)
 assert not any(k in node for k in ['rotation','scale','matrix'])
 trans=node.get('translation',[0,0,0]);mes=j['meshes'][node['mesh']];boxes=[];wire=[]
 for primitive in mes['primitives']:
  acc=j['accessors'][primitive['attributes']['POSITION']];lo=[(acc['min'][i]+trans[i])*1000 for i in range(3)];hi=[(acc['max'][i]+trans[i])*1000 for i in range(3)]
  # Native glTF uses X/right, Y/up, Z/board-down; native STEP uses X/right,Y/up-board,Z/up.
  b=[[lo[0],-hi[2],lo[1]],[hi[0],-lo[2],hi[1]]];boxes.append(b)
  if primitive['material'] in {5,6}:wire.append(b)
 assert len(boxes)==33 and len(wire)==2
 solar[ref]={'bounds_mm':union(boxes),'wire_bounds_mm':union(wire),'component_aabb_clearance_lower_bounds_mm':{part:min(gap(b,records[part]['bounds_mm']) for b in boxes) for part in ['U8','R24','R25','R26','C22']},'positive_wire_aabb_clearance_lower_bounds_mm':{part:min(gap(b,records[part]['bounds_mm']) for b in wire) for part in ['U8','R24','R25','R26','C22']}}
result={'method':'Native KiCad per-reference STEP; board solid excluded; OCCT shape distance. Solar native GLB primitive bounds give conservative lower bounds, not approximate exact surface gaps.','models':records,'solar':solar,'export_sha256':files,'limitations':['Nominal CAD models; no physical build measurement.','Solar dimensions/film/wire placement retain the existing photo-scaled assumptions.','A zero AABB gap is inconclusive and requires exact geometry review.','Package/body registration tolerances must be considered separately.']}
args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
