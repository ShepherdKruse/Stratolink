"""Read-only source comparison and native mechanical geometry checks.

Requires current native-assembly.json, models-pads.json and native copper from
extract_mask_audit.py. Writes only reports beside this script.
"""
from pathlib import Path
import argparse,collections,hashlib,json,sys,copy,subprocess,re
from shapely.geometry import Polygon,Point
from shapely.ops import unary_union

ap=argparse.ArgumentParser();ap.add_argument('--repo',type=Path,required=True);ap.add_argument('--frozen',type=Path,required=True);ap.add_argument('--mask',type=Path,required=True);a=ap.parse_args();repo=a.repo.resolve();frozen=a.frozen.resolve();out=Path(__file__).resolve().parent;live=repo/'hardware/pcb';old=frozen/'hardware/pcb'
def parse(text):
 stack=[];roots=[]
 for token in re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+',text):
  if token=='(':
   item=[];(stack[-1]if stack else roots).append(item);stack.append(item)
  elif token==')':
   assert stack;stack.pop()
  else:
   assert stack;stack[-1].append(json.loads(token)if token.startswith('"')else token)
 assert not stack and len(roots)==1
 return roots[0]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
get=lambda n,k:next((v for v in n if isinstance(v,list)and v and v[0]==k),None)
ref=lambda n:get(n,'property')[2] if get(n,'property')and get(n,'property')[1]=='Reference' else next(v[2]for v in n if isinstance(v,list)and v[:2]==['property','Reference'])
uid=lambda n:get(n,'uuid')[1]if get(n,'uuid')else repr(n[:2])
source=live/'stratolink.kicad_pcb';oldpcb=old/'stratolink.kicad_pcb';h=sha(source);before=source.read_bytes();l=parse(before.decode());b=parse(oldpcb.read_text())
def groups(n):
 d=collections.defaultdict(list)
 for v in n[1:]:
  if isinstance(v,list):d[v[0]].append(v)
 return d
lg,bg=groups(l),groups(b);changed=[]
for k in sorted(set(lg)|set(bg)):
 if lg[k]!=bg[k]:changed.append(k)
lf={ref(v):v for v in lg['footprint']};bf={ref(v):v for v in bg['footprint']};foot=[]
for k in sorted(set(lf)|set(bf)):
 if lf.get(k)==bf.get(k):continue
 x,y=copy.deepcopy(lf[k]),copy.deepcopy(bf[k])
 for q in [x,y]:
  for p in q:
   if isinstance(p,list)and p[:2]==['property','Value']:p[:]=[v for v in p if not(isinstance(v,list)and v and v[0]=='hide')]
 foot.append({'ref':k,'difference_only_value_field_visibility':x==y})
route=[]
for typ in ['segment','arc','via','zone']:
 cur={uid(v):v for v in lg[typ]};prev={uid(v):v for v in bg[typ]}
 for k in sorted(set(cur)|set(prev)):
  if cur.get(k)!=prev.get(k):route.append({'type':typ,'uuid':k,'before':prev.get(k),'after':cur.get(k)})
def asset_names(root):
 return {str(p.relative_to(root))for d in ['lib','3d']for p in (root/d).rglob('*')if p.is_file()and '__pycache__'not in p.parts and p.suffix!='.pyc'}
assets=sorted(asset_names(live)|asset_names(old))
identities={}
for name in ['stratolink.kicad_pcb','stratolink.kicad_sch','stratolink.kicad_pro','stratolink.kicad_dru','fp-lib-table','sym-lib-table']+assets:
 cur=live/name;prev=old/name;identities[name]={'live_sha256':sha(cur)if cur.is_file()else None,'frozen_sha256':sha(prev)if prev.is_file()else None}
proj=json.loads((live/'stratolink.kicad_pro').read_text());oldproj=json.loads((old/'stratolink.kicad_pro').read_text())
r={'live_pcb_sha256':h,'frozen_commit':subprocess.check_output(['git','-C',str(frozen),'rev-parse','HEAD'],text=True).strip(),'frozen_pcb_sha256':sha(oldpcb),'changed_board_top_level_groups':changed,'footprint_differences':foot,'route_or_zone_differences':route,'setup_equal':lg['setup']==bg['setup'],'layers_equal':lg['layers']==bg['layers'],'edge_cuts_equal':[v for v in l if isinstance(v,list)and get(v,'layer')==['layer','Edge.Cuts']]==[v for v in b if isinstance(v,list)and get(v,'layer')==['layer','Edge.Cuts']],'all_assets_equal':all(identities[p]['live_sha256']==identities[p]['frozen_sha256']for p in assets),'asset_file_count':len(assets),'source_identities':identities,'mask_project_settings':{side:{'solder_mask_bridge':p['board']['design_settings']['rule_severities']['solder_mask_bridge'],'solder_mask_to_copper_clearance_mm':p['board']['design_settings']['rules']['solder_mask_to_copper_clearance']}for side,p in [('live',proj),('frozen',oldproj)]}}
(out/'source-comparison.json').write_text(json.dumps(r,indent=2)+'\n')
j=json.loads((out/'native-assembly.json').read_text());n=json.loads((out/'models-pads.json').read_text());c=json.loads((a.mask/'native-copper.json').read_text());assert j['sha256']==n['sha256']==c['pcb_sha256']==h
union=lambda ps:unary_union([Polygon(v['shell'],v['holes']).buffer(0)for v in ps]);board=union(j['outline']);near=[]
for p in c['copper']:
 if p['ref']not in ['PCB_TRACK','PCB_ARC','PCB_VIA']:continue
 q=union(p['polygons']);near.append({'type':p['ref'],'uuid':p['uuid'],'net':p['net'],'face':p['face'],'edge_gap_mm':q.distance(board.boundary),'outside_board_mm2':q.difference(board).area})
rings=[]
for p in j['pads']:
 if not max(p['drill'])or p['net']=='':continue
 assert abs(p['drill'][0]-p['drill'][1])<1e-8
 q=union(p['polygons']);center=Point(p['at']);radius=p['drill'][0]/2
 rings.append({'ref':p['ref'],'pin':p['pin'],'layer':p['layer'],'at_mm':p['at'],'hole_mm':p['drill'][0],'minimum_radial_copper_mm':q.boundary.distance(center)-radius,'hole_edge_ligament_mm':center.distance(board.boundary)-radius,'net':p['net']})
slits={}
for name in ['J1','J2','H1','H2','AE1','AE2','J3','J4']:
 f=n['footprints'][name];slits[name]={'at_mm':f['at'],'angle':f['angle'],'layer':f['layer'],'pads':f['pads'],'explicit_pad_zone_settings':[{key:get(p,key)for key in ['net','zone_connect','thermal_gap','thermal_bridge_width','thermal_bridge_angle']if get(p,key)}for p in lf[name]if isinstance(p,list)and p[0]=='pad']}
silks={}
for suffix in ['F_Silkscreen.gto','B_Silkscreen.gbo']:
 path=a.mask/('stratolink-'+suffix);lines=path.read_text().splitlines();draw=[v for v in lines if ('D01*'in v or 'D03*'in v)and not v.startswith('G04')];silks[suffix]={'sha256':sha(path),'draw_flash_commands':len(draw)}
def artwork(path):
 return '\n'.join(v for v in path.read_text().splitlines()if not v.startswith(('%TF.CreationDate,','G04 Created by KiCad')))
art=[]
for suffix in ['F_Mask.gts','B_Mask.gbs','F_Silkscreen.gto','B_Silkscreen.gbo','Edge_Cuts.gm1']:
 path=a.mask/('stratolink-'+suffix);prior=repo/'hardware/gerbers/v1.1-pilot-supplier-20261016/gerbers'/path.name
 art.append({'file':path.name,'live_sha256':sha(path),'Y25_sha256':sha(prior),'equal_except_creation_timestamps':artwork(path)==artwork(prior)})
assert all(v['equal_except_creation_timestamps']for v in art)
(out/'Y25-artwork-comparison.json').write_text(json.dumps({'pcb_sha256':h,'comparison':'All exact Gerber content except TF.CreationDate and G04 Created by KiCad timestamp lines. No aperture, coordinate, attribute, draw or flash commands removed.','files':art},indent=2)+'\n')
vias=[v for v in n['holes']if v['ref']=='via'];ordinary=[v for v in rings if v['ref']!='U1'];zone_settings=[]
for z in lg['zone']:
 zone_settings.append({key:get(z,key)for key in ['uuid','net','layer','layers','connect_pads','min_thickness','fill','filled_areas_thickness']if get(z,key)})
r2={'pcb_sha256':h,'outline_valid':board.is_valid,'outline_area_mm2':board.area,'outline_bounds_mm':list(board.bounds),'outline_parts':len(board.geoms)if hasattr(board,'geoms')else 1,'board_thickness_mm':n['thickness_mm'],'stackup':get(lg['setup'][0],'stackup'),'board_mask_min_width':get(lg['setup'][0],'solder_mask_min_width'),'silkscreen_native_items':n['silk'],'silkscreen_gerbers':silks,'minimum_ordinary_component_ring_mm':min(v['minimum_radial_copper_mm']for v in ordinary),'minimum_U1_thermal_ring_mm':min(v['minimum_radial_copper_mm']for v in rings if v['ref']=='U1'),'minimum_ordinary_via_ring_mm':min(v['nominal_min_annulus_mm']for v in vias),'component_ring_measurements':rings,'nearest_routed_copper_to_edge':sorted(near,key=lambda v:v['edge_gap_mm'])[:20],'mechanical_features':slits,'zone_settings':zone_settings,'limits':['Effective native copper polygons and circular-hole radii; polygon tessellation can change rounded-boundary values by micrometers.','Saved ground fills are used here. Electrical review separately refills and checks the exact repaired final board.','No measured solder envelope, thermal/vibration proof, antenna-pattern qualification or supplier CAM approval.']}
(out/'geometry-review.json').write_text(json.dumps(r2,indent=2)+'\n');assert source.read_bytes()==before
print(json.dumps({'PCB':h,'changed_groups':changed,'footprint_diff':foot,'route_zone_differences':len(route),'assets_equal':r['all_assets_equal'],'annulus_component_mm':r2['minimum_ordinary_component_ring_mm'],'annulus_thermal_mm':r2['minimum_U1_thermal_ring_mm'],'annulus_via_mm':r2['minimum_ordinary_via_ring_mm'],'nearest_routed_edge':r2['nearest_routed_copper_to_edge'][:2],'silk':silks},indent=2))
