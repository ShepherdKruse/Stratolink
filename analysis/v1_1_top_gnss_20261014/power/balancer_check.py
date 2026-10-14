from pathlib import Path
import argparse,json,math,heapq
from shapely.geometry import Polygon,LineString,Point
from shapely.ops import unary_union
ap=argparse.ArgumentParser();ap.add_argument('--baseline',type=Path,required=True);ap.add_argument('--candidate',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args();before=json.loads(args.baseline.read_text());after=json.loads(args.candidate.read_text());geo=lambda p:unary_union([Polygon(q['shell'],q['holes'])for q in p['polygons']]);out=[]
# Trace arc centerline via circumcircle through start/mid/end, with native length enforcing sweep.
def path(t):
 a=t['start'];b=t['end']
 if t['kind']!='PCB_ARC':return LineString([a,b])
 m=t['mid'];D=2*(a[0]*(m[1]-b[1])+m[0]*(b[1]-a[1])+b[0]*(a[1]-m[1]));A=a[0]**2+a[1]**2;M=m[0]**2+m[1]**2;B=b[0]**2+b[1]**2;cx=(A*(m[1]-b[1])+M*(b[1]-a[1])+B*(a[1]-m[1]))/D;cy=(A*(b[0]-m[0])+M*(a[0]-b[0])+B*(m[0]-a[0]))/D;r=math.dist(a,[cx,cy]);th=math.atan2(a[1]-cy,a[0]-cx);end=math.atan2(b[1]-cy,b[0]-cx);mid=math.atan2(m[1]-cy,m[0]-cx);delta=(end-th)%(2*math.pi)
 if (mid-th)%(2*math.pi)>delta+1e-6:delta-=2*math.pi
 return LineString([(cx+r*math.cos(th+delta*i/64),cy+r*math.sin(th+delta*i/64))for i in range(65)])
for j in[before,after]:
 switch=unary_union([geo(p)for p in j['pads']if p['net']=='Net-(U1-LBOOST)']+[path(t).buffer(t['width']/2,resolution=32)for t in j['tracks']if t['net']=='Net-(U1-LBOOST)'and t['kind']!='PCB_VIA']);row=dict(sha256=j['sha256'],opposite_face_switch_overlap=[])
 for net in['/SC_BAL_OUT','/VBAT','/SC_HALF_REF']:
  front=unary_union([path(t).buffer(t['width']/2,resolution=32)for t in j['tracks']if t['net']==net and t['layer']=='F.Cu'and t['kind']!='PCB_VIA']);inter=front.intersection(switch);row['opposite_face_switch_overlap'].append(dict(net=net,projected_overlap_mm2=inter.area,bounds_mm=list(inter.bounds)if not inter.is_empty else None))
 # local feedback/bypass paths are preserved/short local traces in final candidate, provide exact total.
 ts=[t for t in j['tracks']if t['net']=='/SC_BAL_OUT' and t['layer']=='B.Cu' and t['kind']=='PCB_TRACK' and max(t['start'][0],t['end'][0])<57.8 and min(t['start'][1],t['end'][1])>34];row['local_feedback_route_length_mm']=sum(t['length']for t in ts);row['local_feedback_route_tracks']=ts
 if j is after:row['C22_positive_to_U8_VBAT_path_mm']=.65+math.dist([56.7875,37.7],[56.08,38.3])
 out.append(row)
report=dict(snapshots=out,notes=['Projected trace-to-switch copper overlap is geometry, not a coupling simulation. Includes customL1 switch land and U1switchpad; circles/arcs approximated finely.','Balancer output andVBAT are lowerimpedance thanSC_HALF_REF; lattershowsno suchcrossing. Newoverlapdoesnotprovefunctionalnoise butshouldremainexplicitinbenchvalidation.','Nativefullnetconnectivity and localfeedbackpinconnection mustindependentlypass.'])
args.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps([{k:v for k,v in r.items()if k!='local_feedback_route_tracks'}for r in out],indent=2))
