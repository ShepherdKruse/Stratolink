from pathlib import Path
import sys,json,math
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from shapely.plotting import patch_from_polygon
from shapely.geometry import Polygon,Point,box
from shapely.ops import unary_union
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'analysis/v1_1_peer_review_20261014/digital'))
from check_rf_reference import polygons,centerline,parts
out=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).parent
d=json.loads((out/'native-copper.json').read_text());s=json.loads((out/'native-layout.json').read_text())
assert d['pcb_sha256']==s['sha256'], 'Mismatched native snapshots'
items=[dict(i,g=polygons(i['polygons']))for i in d['items']]
net=lambda n,l:unary_union([i['g']for i in items if i['net']==n and i['layer']==l])
pad=lambda r,p:next(i for i in items if i.get('ref')==r and i.get('pin')==p)
report={'pcb_sha256':d['pcb_sha256'],'switch_nodes':{},'RF':{},'bypass':{},'balancer':{}}
for name in ['LBOOST','LBUCK']:
 n='Net-(U1-'+name+')';g=net(n,'B.Cu');other=[]
 for i in items:
  if i['layer']=='F.Cu' and i['net']not in ['GND',n] and i['g'].intersection(g).area>1e-8:
   other.append({k:i[k]for k in ['net','kind','uuid','ref','pin']if k in i}|{'overlap_mm2':i['g'].intersection(g).area,'bounds_mm':list(i['g'].intersection(g).bounds)})
 report['switch_nodes'][name]={'net':n,'area_mm2':g.area,'bounds_mm':list(g.bounds),'opposite_face_non_ground':other}
for ae in ['AE2','AE1']:
 n='Net-('+ae+'-A)';rf=net(n,'F.Cu');tr=[i for i in items if i['net']==n and i['layer']=='F.Cu' and 'start'in i];path=unary_union([centerline(i)for i in tr]);antenna=pad(ae,'1')['g'];gnd=net('GND','B.Cu');missing=path.difference(antenna.buffer(.15)).difference(gnd.buffer(.005));foreign=[]
 for i in items:
  if i['layer']=='B.Cu' and i['net'] not in ['GND',n]:
   overlap=rf.difference(antenna.buffer(.15)).intersection(i['g'])
   if overlap.area>1e-8:foreign.append({k:i[k]for k in ['net','kind','uuid','ref','pin']if k in i}|{'overlap_mm2':overlap.area,'bounds_mm':list(overlap.bounds)})
 report['RF'][ae]={'whole_net_centerline_length_mm':path.length,'missing_rear_reference_centerline_mm_beyond_antenna_0_15mm_buffer_and_5um_tolerance':missing.length,'missing_reference_wkt':missing.wkt,'foreign_rear_projection':foreign,'minimum_copper_edge_to_LBOOST_mm':rf.distance(net('Net-(U1-LBOOST)','B.Cu')),'minimum_copper_edge_to_LBUCK_mm':rf.distance(net('Net-(U1-LBUCK)','B.Cu'))}
for r,p,target,tp in [('C10','1','U3','8'),('C10','2','U3','5'),('C22','1','U8','5'),('C7','2','U2','24'),('C8','2','U2','24')]:
 a,b=pad(r,p),pad(target,tp)
 report['bypass'][r+'.'+p+'-'+target+'.'+tp]={'pad_center_distance_mm':math.dist(a['at'],b['at']),'a_net':a['net'],'b_net':b['net']}
for n in ['/SC_HALF_REF','/SC_BAL_OUT','/VBAT']:
 g=net(n,'F.Cu');report['balancer'][n]={'switch_overlap_mm2':sum(g.intersection(net('Net-(U1-'+k+')','B.Cu')).area for k in ['LBOOST','LBUCK']),'track_length_mm':sum(i.get('length_mm',0)for i in items if i['net']==n and i['layer']=='F.Cu' and 'start'in i)}
for label,extent in [('upper',[52.5,77,29,55]),('lower',[53,77,56,84]),('rf-launch',[58,65,42,48])]:
 fig,ax=plt.subplots(figsize=(11,11))
 for l,n,c,a in [('B.Cu','GND','#bcd9f2',.7),('F.Cu','GND','#b2d8bb',.35),('B.Cu','Net-(U1-LBOOST)','#f94721',.95),('B.Cu','Net-(U1-LBUCK)','#ffb636',.95),('B.Cu','/VBAT','#b064ad',.85),('B.Cu','/SC_MID','#93969c',.85),('F.Cu','Net-(AE2-A)','#b20d0d',.95),('F.Cu','Net-(AE1-A)','#b20d0d',.95),('F.Cu','Net-(U3-VCC)','#dc9332',.95),('F.Cu','/SC_HALF_REF','#0d70b2',.95),('F.Cu','/SC_BAL_OUT','#dc3290',.95)]:
  for p in parts(net(n,l)):
   ax.add_patch(patch_from_polygon(p,facecolor=c,alpha=a,lw=.2,edgecolor=c))
 for ref in ['AE1','AE2','U1','U2','U3','U8','L1','L2','D3','C2','C3','C4','C6','C7','C8','C10','FB1','C22','R24','R25','R26']:
  x,y=s['footprints'][ref]['at']
  if extent[0]<x<extent[1]and extent[2]<y<extent[3]:ax.text(x,y,ref,fontsize=8,ha='center',bbox=dict(facecolor='white',alpha=.8,pad=1,lw=0))
 ax.legend(handles=[Patch(facecolor=c,label=l)for c,l in [('#bcd9f2','Rear ground'),('#b2d8bb','Front ground'),('#b20d0d','Front RF'),('#b064ad','Rear VBAT'),('#93969c','Rear midpoint'),('#f94721','Rear boost switch'),('#ffb636','Rear buck switch'),('#dc9332','Front GNSS supply')]],loc='upper center',bbox_to_anchor=(.5,-.05),ncol=4,fontsize=8)
 ax.set_xlim(extent[0],extent[1]);ax.set_ylim(extent[3],extent[2]);ax.set_aspect('equal');ax.grid(alpha=.15);ax.set_title(label+': actual saved copper, front and rear projection');fig.savefig(out/(label+'.png'),dpi=170,bbox_inches='tight');plt.close(fig)
report['rf_projection_pass']=all(not x['foreign_rear_projection']and x['missing_rear_reference_centerline_mm_beyond_antenna_0_15mm_buffer_and_5um_tolerance']<1e-8 for x in report['RF'].values())
assert report['rf_projection_pass']
report['limits']=['Native saved fills from the final root-refilled board; read-only extraction, no CAD modification by this final checker.','Pad center distances do not determine bypass inductance.','Projected overlaps and clearance are not RF/noise performance or impedance qualification.','Foreign-net names resolved from present native pins and all filled zones included; no fixed old switch-track assumptions.']
(out/'rf-power-review.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
