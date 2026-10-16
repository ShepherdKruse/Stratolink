"""Compare actual KiCad mask Gerbers to same-revision native copper."""
from pathlib import Path
import sys,json
from shapely.geometry import Polygon,Point
from shapely.ops import unary_union
source=Path(sys.argv[1]);output=Path(sys.argv[2]);j=json.loads((source/'native-copper.json').read_text());union=lambda ps:unary_union([Polygon(p['shell'],p['holes']).buffer(0)for p in ps]);copper=[(v,union(v['polygons']))for v in j['copper']];masks={};identities={}
for face in ['F','B']:
 r=json.loads((source/(face+'-regions.json')).read_text());identities[face]=r['gerber_sha256'];g=unary_union([Polygon(v[0],v[1:])for v in r['regions']]);masks[face]=list(g.geoms)if hasattr(g,'geoms')else[g]
rows=[]
for p in j['targets']:
 c=union(p['polygons']);hit=[g for g in masks[p['face']]if g.contains(Point(p['at']))];assert len(hit)==1;(g,)=hit
 nearest=min([(g.distance(cg),v)for v,cg in copper if v['face']==p['face']and v['net']!=p['net']and not cg.is_empty],key=lambda q:q[0]);others=[g.distance(v)for v in masks[p['face']]if v!=g]
 rows.append({'ref':p['ref'],'pin':p['pin'],'net':p['net'],'face':p['face'],'fully_exposed':c.difference(g).area<1e-9,'opening_minimum_copper_edge_clearance_mm':c.distance(g.boundary),'opening_to_foreign_copper_mm':nearest[0],'nearest_foreign':{k:v for k,v in nearest[1].items()if k not in['polygons','at']},'minimum_web_to_other_aperture_mm':min(others)})
assert all(r['fully_exposed']and r['opening_to_foreign_copper_mm']>=.0899 and r['minimum_web_to_other_aperture_mm']>=.0999 for r in rows)
summary={}
for ref in ['U1','U4','L2']:
 rs=[r for r in rows if r['ref']==ref];summary[ref]={'pad_count':len(rs),'minimum_opening_to_foreign_copper_mm':min(r['opening_to_foreign_copper_mm']for r in rs),'minimum_mask_web_mm':min(r['minimum_web_to_other_aperture_mm']for r in rs),'minimum_opening_to_own_copper_edge_mm':min(r['opening_minimum_copper_edge_clearance_mm']for r in rs)}
report={'pcb_sha256':j['pcb_sha256'],'mask_gerber_sha256':identities,'all30_target_lands_fully_exposed':True,'all_target_mask_foreign_gaps_at_least009mm':True,'all_target_mask_webs_at_least010mm':True,'summary':summary,'pads':rows,'limits':'Native plotted geometry; KiCad polygon tessellation affects rounded-edge distances by micrometers. JLC registration, mask tent integrity and factory CAM remain unqualified. The check is scoped to U1 perimeter, U4 and L2, not a claim that every board aperture uses this generic mask rule.'};output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(summary,indent=2))
