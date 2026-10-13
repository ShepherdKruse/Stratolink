import gzip
from pathlib import Path
import json
from shapely.geometry import Polygon,box
from shapely.ops import unary_union
H=Path(__file__).resolve().parent;d=json.loads(gzip.decompress((H/'selected-regions.json.gz').read_bytes()))
def poly(items):return unary_union([Polygon(p['shell'],p['holes']) for p in items if len(p['shell'])>=3])
body=box(69.548,36.807,71.548,38.807);rois={'U7':box(69,35.5,73,40),'J20':box(60.5,83.3,63,85.7)};roi=unary_union(list(rois.values()));rows={};fills={};copper={}
for label,t in d.items():
 f={l:poly(z) for l,z in t['zones'].items()};fills[label]=f
 copper[label]=unary_union([f['0']]+[poly(i['polygons']) for i in t['items']])
 contacts={}
 for i in t['items']:
  if (i.get('ref')=='U7' and i.get('pin') in ['3','5','6','7','8']) or (i.get('ref')=='J20' and i.get('pin')=='5'):
   p=poly(i['polygons']);inter=f['0'].intersection(p)
   contacts[f"{i['ref']}.{i['pin']}"]=dict(pad_area_mm2=p.area,zone_overlap_area_mm2=inter.area,zone_distance_mm=p.distance(f['0']),pad_boundary_overlap_mm=f['0'].intersection(p.boundary).length)
 rows[label]=dict(U7_nominal_body_total_copper_mm2=copper[label].intersection(body).area,U7_nominal_body_zone_fill_mm2=f['0'].intersection(body).area,pad_fill_contacts=contacts)
changes={}
for layer in ['0','2']:
 if layer not in fills['baseline']:continue
 a,b=fills['baseline'][layer],fills['selected'][layer];added=b.difference(a);removed=a.difference(b);delta=a.symmetric_difference(b)
 changes[layer]=dict(added_area_mm2=added.area,removed_area_mm2=removed.area,outside_rois_area_mm2=delta.difference(roi).area,components_bounds_mm=[list(p.bounds) for p in (list(delta.geoms) if hasattr(delta,'geoms') else [delta]) if p.area>1e-8])
a,b=copper['baseline'],copper['selected'];changes['F.Cu_total']=dict(added_area_mm2=b.difference(a).area,removed_area_mm2=a.difference(b).area,U7_body_added_mm2=b.difference(a).intersection(body).area,U7_body_removed_mm2=a.difference(b).intersection(body).area,outside_rois_mm2=a.symmetric_difference(b).difference(roi).area,outside_rois_added_beyond_2nm_mm2=b.difference(a.buffer(0.000002)).difference(roi).area,outside_rois_removed_beyond_2nm_mm2=a.difference(b.buffer(0.000002)).difference(roi).area)
result=dict(units='mm and mm^2',approximation_error_mm=0.0001,body_roi_mm=list(body.bounds),regions={k:list(v.bounds) for k,v in rois.items()},measurements=rows,changes=changes)
(H/'geometry-measurements.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
# Adapt previous native geometry plotting routine, without changing its archived output.
s=(H/'plot_regions.py').read_text().replace("d=json.loads(gzip.decompress((H/'regions.json.gz').read_bytes()))","d=json.loads(gzip.decompress((H/'selected-regions.json.gz').read_bytes()));d={k:dict(v,zones=v['zones']['0']) for k,v in d.items()}").replace('baseline and rejected mixed-angle trial','baseline and explicit trace-fed candidate').replace('Pad7 remains starved in trial.','U7 pads 5/7/8: local no-zone; J20 pad 5: local solid.').replace("'regions-before-trial.png'","'regions-before-selected.png'")
exec(compile(s,str(H/'plot_regions.py'),'exec'))
