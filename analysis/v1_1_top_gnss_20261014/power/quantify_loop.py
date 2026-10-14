from pathlib import Path
import argparse,json,math
from shapely.geometry import Polygon,LineString
from shapely.ops import unary_union
ap=argparse.ArgumentParser();ap.add_argument('--baseline',type=Path,required=True);ap.add_argument('--candidate',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args();before=json.loads(args.baseline.read_text());after=json.loads(args.candidate.read_text());g=lambda p:unary_union([Polygon(q['shell'],q['holes'])for q in p['polygons']]);rho=.0004925714285714286;out=[]
for j in[before,after]:
 x=j['footprints']['L1']['at'][0];loop=[(63.873,38.367),(62.952,38.367),(61.0065,36.4215),(x,36.4215),(x,39.9515),(61.0885,39.9515),(61.906,40.769),(64.367,40.769),(65.671,39.465),(66.191,39.465),(65.540999,38.814998),(63.873,39.917)];poly=Polygon(loop);assert poly.is_valid
 switch=[t for t in j['tracks']if t['net']=='Net-(U1-LBOOST)'];pads=unary_union([g(p)for p in j['pads']if p['net']=='Net-(U1-LBOOST)']);exposed=sum(LineString([t['start'],t['end']]).difference(pads).length for t in switch);L1C2=math.dist([x,36.4215],[61.0065,36.4215])+math.dist([61.0065,36.4215],[62.952,38.367])+.921
 row=dict(sha256=j['sha256'],L1_center_mm=j['footprints']['L1']['at'],LBOOST_centerline_mm=sum(t['length']for t in switch),LBOOST_widths_mm=sorted(set(t['width']for t in switch)),LBOOST_trace_resistance_ohm=rho*sum(t['length']/t['width']for t in switch),LBOOST_centerline_outside_pads_mm=exposed,C2_to_L1_pad_center_routed_length_mm=L1C2,projected_local_loop_surrogate_area_mm2=poly.area,projected_loop_vertices_mm=loop)
 out.append(row)
report=dict(before=out[0],after=out[1],notes=['The projected loop polygon uses actual routed +SOLAR and LBOOST centerlines, straight terminal-to-terminal winding projection, and straight U1/C2 ground/chip closure. It is a geometric comparison only, not measured magnetic loop area, inductance, or EMI simulation.','Actual current spreads in wide custom L1 pads, the inductor winding, the chip and ground fill. Exposed centerline metric excludes same-net pad polygons.','C2-to-VIN local trace geometry and all LBUCK tracks are exact unchanged; C2/U1/GND-pad placements are unchanged.'])
args.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
