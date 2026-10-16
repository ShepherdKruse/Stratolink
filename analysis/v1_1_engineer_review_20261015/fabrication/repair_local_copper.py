#!/usr/bin/env python3
"""Fill one UV ground-pour notch and shorten the redundant L1 supply loop.
Only one existing zone outline and three existing track nodes may change.
Footprints, pad geometry, other routing and branding stay unchanged.
"""
from pathlib import Path
import argparse,hashlib,json
import pcbnew,wx
ZONE_UUID='442a117e-a323-4a64-825c-b874c2426d48'
BEFORE=[(74.97,37.07),(75.57,37.07),(75.57,38.72),(75.18,38.72),(75.18,39.25),(74.32,39.25),(74.32,38.72),(73,38.72),(73,36.51),(74.97,36.51)]
AFTER=[(74.97,37.07),(75.57,37.07),(75.57,39.25),(74.32,39.25),(74.32,38.72),(73,38.72),(73,36.51),(74.97,36.51)]
def apply_uv_corner(board):
 zones=[z for z in board.Zones()if z.m_Uuid.AsString()==ZONE_UUID];assert len(zones)==1
 z=zones[0];assert z.GetNetname()=='GND'and z.GetLayer()==pcbnew.F_Cu
 p=z.Outline();assert p.OutlineCount()==1 and p.HoleCount(0)==0
 pts=[(p.Outline(0).CPoint(i).x/1e6,p.Outline(0).CPoint(i).y/1e6)for i in range(p.Outline(0).PointCount())];assert pts==BEFORE,pts
 p.RemoveAllContours();p.NewOutline()
 for x,y in AFTER:p.Append(round(x*1e6),round(y*1e6))
 return {'zone_uuid':ZONE_UUID,'before_outline_mm':BEFORE,'after_outline_mm':AFTER,'nominal_outline_added_area_mm2':.39*.53,'reason':'Fill the small enclosed non-copper void created where the UV GND zone meets the main GND fill at its concave corner. Native refill determines actual final copper; no signal route changes.'}

UUID='59f56b85-79d6-4fa5-a321-83138da340a4'
def apply_l1_tail(b):
 ts=[t for t in b.GetTracks()if t.m_Uuid.AsString()==UUID];assert len(ts)==1;t=ts[0]
 assert t.GetNetname()=='+SOLAR'and t.GetLayer()==pcbnew.B_Cu and t.GetWidth()==300000
 assert list(t.GetStart())==[69590000,36510000]and list(t.GetEnd())==[71895000,34205000]
 t.SetEnd(pcbnew.VECTOR2I(71300000,34800000))
 for uid in ['a95ef473-602c-4498-b8da-af0e3a9c76e0','18d2448d-ccf2-4af7-8ca3-9489ea76f57a']:
  stub=[s for s in b.GetTracks()if s.m_Uuid.AsString()==uid];assert len(stub)==1 and stub[0].GetNetname()=='+SOLAR';b.Remove(stub[0])
 return {'track_uuid':UUID,'start_mm':[69.59,36.51],'before_end_mm':[71.895,34.205],'after_end_mm':[71.3,34.8],'width_mm':.3,'removed_stub_uuids':['a95ef473-602c-4498-b8da-af0e3a9c76e0','18d2448d-ccf2-4af7-8ca3-9489ea76f57a'],'shortened_tail_removed_centerline_mm':(.595**2*2)**.5,'deleted_loop_segments_mm':[0.275,(0.6**2*2)**.5],'total_removed_centerline_mm':(.595**2*2)**.5+0.275+(0.6**2*2)**.5,'reason':'Shorten the diagonal tail to terminate in L1.2 and remove its two redundant loop segments, opening the enclosed triangular etch pocket. The retained trace follows the same centerline; the footprint is unchanged.'}

def apply(board):
 return {'uv_corner':apply_uv_corner(board),'l1_tail':apply_l1_tail(board)}
if __name__=='__main__':
 p=argparse.ArgumentParser(description='Apply two bounded copper corrections to the hash-bound root candidate. Refill and verify using native KiCad afterward.');p.add_argument('--pcb',type=Path,required=True);p.add_argument('--ledger',type=Path,required=True);p.add_argument('--expected-sha256',default='2d053c2743dad1d834eb1a661f202d727ce1ae8c6000656aaaaa282769c000ab');a=p.parse_args()
 before=hashlib.sha256(a.pcb.read_bytes()).hexdigest();assert before==a.expected_sha256,(before,a.expected_sha256)
 app=wx.App(False);b=pcbnew.LoadBoard(str(a.pcb));r=apply(b);pcbnew.SaveBoard(str(a.pcb),b);r['before_pcb_sha256']=before;r['after_unfilled_pcb_sha256']=hashlib.sha256(a.pcb.read_bytes()).hexdigest();a.ledger.write_text(json.dumps(r,indent=2)+'\n')
