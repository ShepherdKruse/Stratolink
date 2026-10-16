#!/usr/bin/env python3
"""Report physical power-layout continuity across the bounded repair pass."""
from pathlib import Path
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'analysis/v1_1_peer_review_20261014/digital'))
from check_rf_reference import polygons,parts
from shapely.geometry import Point
from shapely.ops import unary_union
p=argparse.ArgumentParser();p.add_argument('--before-layout',type=Path,required=True);p.add_argument('--before-copper',type=Path,required=True);p.add_argument('--final-dir',type=Path,default=Path(__file__).parent);a=p.parse_args()
b=json.loads(a.before_layout.read_text());bc=json.loads(a.before_copper.read_text());f=json.loads((a.final_dir/'native-layout.json').read_text());fc=json.loads((a.final_dir/'native-copper.json').read_text());assert b['sha256']==bc['pcb_sha256'] and f['sha256']==fc['pcb_sha256']
crit=['U1','L1','L2','C2','C3','C4','C6','C8','C21','C10','FB1','U8','C22','R24','R25','R26']
retained={r:all(b['footprints'][r][k]==f['footprints'][r][k]for k in ['at','angle','layer','value'])for r in crit}
rows=[]
for net in ['Net-(U1-LBOOST)','Net-(U1-LBUCK)','Net-(U3-VCC)','/SC_HALF_REF','/SC_BAL_OUT']:
 for layer in ['F.Cu','B.Cu']:
  def geo(d):return unary_union([polygons(i['polygons'])for i in d['items']if i['net']==net and i['layer']==layer])
  before,after=geo(bc),geo(fc);rows.append({'net':net,'layer':layer,'before_area_mm2':before.area,'after_area_mm2':after.area,'symmetric_difference_mm2':before.symmetric_difference(after).area})
solar_items=[i for i in fc['items']if i['net']=='+SOLAR'and i['layer']=='B.Cu']
solar_geo=unary_union([polygons(i['polygons'])for i in solar_items]);solar_parts=parts(solar_geo)
solar_pads=[next(i for i in solar_items if i.get('ref')==r and i.get('pin')==pin)for r,pin in [('C2','1'),('L1','2'),('U1','2')]]
contact_sets=[{j for j,g in enumerate(solar_parts)if g.intersects(polygons(i['polygons']))}for i in solar_pads]
wide='1672ba16-99bb-49ca-9585-e689cab390bb';entry='59f56b85-79d6-4fa5-a321-83138da340a4'
bt={i['uuid']:i for i in b['tracks']};ft={i['uuid']:i for i in f['tracks']};end=Point(ft[entry]['end']);l1=polygons(solar_pads[1]['polygons'])
solar={'C2_to_L1_wide_track_unchanged':bt[wide]==ft[wide],'wide_track_width_mm':ft[wide]['width'],'wide_track_length_mm':ft[wide]['length'],'C2_L1_U1_VIN_connected_in_rear_copper':bool(set.intersection(*contact_sets)),'U1_supply_branch_endpoint_mm':ft[entry]['end'],'endpoint_inside_L1_positive_land':l1.covers(end),'endpoint_to_land_boundary_mm':l1.boundary.distance(end),'removed_redundant_branch_UUIDs':[u for u in ['18d2448d-ccf2-4af7-8ca3-9489ea76f57a','a95ef473-602c-4498-b8da-af0e3a9c76e0']if u in bt and u not in ft]}
assert solar['C2_to_L1_wide_track_unchanged']and solar['C2_L1_U1_VIN_connected_in_rear_copper']and solar['endpoint_inside_L1_positive_land']and len(solar['removed_redundant_branch_UUIDs'])==2
out={'incoming_pcb_sha256':b['sha256'],'pcb_sha256':f['sha256'],'critical_poses_values_retained':retained,'critical_copper':rows,'solar_connection':solar,'pass':all(retained.values())and all(r['symmetric_difference_mm2']<1e-8 for r in rows),'limits':['Comparison covers listed local switching, GNSS supply, and balancer reference/output copper on both faces, including all filled zones. It does not assert all board routing unchanged.','Ground intentionally changes to reconnect previously isolated networks and restore RF reference; root netlist/DRC and ground-review.json check those connections.','Geometric continuity of retained circuit regions is not a transient, EMI, or cold-start qualification.']}
(a.final_dir/'power-continuity.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2));assert out['pass']
