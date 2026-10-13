#!/usr/bin/env python3
"""Independent OCCT import/solid/volume check; no model edits."""
from OCP.STEPControl import STEPControl_Reader
from OCP.IFSelect import IFSelect_ItemsByEntity
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.TopAbs import TopAbs_SOLID,TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp
import io,json,math,pathlib
HERE=pathlib.Path(__file__).resolve().parent;root=HERE.parents[2];new=pathlib.Path(json.loads((HERE/'candidate.json').read_text())['candidate'])/'lib';out=[]
for p,length in [(root/'hardware/pcb/lib/gps.step',45.6),(new/'Stratolink_Wire_82mm_D0p321_Nominal.step',82),(new/'Stratolink_Wire_48mm_D0p321_Nominal.step',48)]:
 r=STEPControl_Reader();status=r.ReadFile(str(p));s=io.BytesIO();r.PrintCheckLoad(s,False,IFSelect_ItemsByEntity);loaded=s.getvalue().decode();r.TransferRoots();shape=r.OneShape();counts={}
 for name,typ in [('solids',TopAbs_SOLID),('faces',TopAbs_FACE)]:
  e=TopExp_Explorer(shape,typ);n=0
  while e.More():n+=1;e.Next()
  counts[name]=n
 b=Bnd_Box();BRepBndLib.AddOptimal_s(shape,b);v=GProp_GProps();BRepGProp.VolumeProperties_s(shape,v,1e-10);mn=b.CornerMin();mx=b.CornerMax()
 d=dict(file=str(p),status=str(status),load_checks=loaded,valid_brep=BRepCheck_Analyzer(shape).IsValid(),bounds_mm=[[mn.X(),mn.Y(),mn.Z()],[mx.X(),mx.Y(),mx.Z()]],volume_mm3=v.Mass(),counts=counts,nominal_feed_to_tip_mm=length)
 assert d['valid_brep'] and counts=={'solids':1,'faces':8},d
 assert abs(mx.Z()-length)<1e-5 and abs(mx.X()-.321)<1e-5 and abs(mn.Y()+2)<1e-5
 if out:
  expected=(length-45.6)*math.pi*(.321/2)**2;actual=v.Mass()-out[0]['volume_mm3'];assert abs(expected-actual)/expected<0.001,(expected,actual)
  d['added_volume_mm3']=actual;d['ideal_cylinder_extension_mm3']=expected;d['relative_volume_difference']=abs(expected-actual)/expected
 out.append(d)
print(json.dumps(out,indent=2));(HERE/'model-kernel-review.json').write_text(json.dumps(out,indent=2)+'\n')
