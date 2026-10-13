#!/usr/bin/env python3
"""Independent complete copper XOR and explicit zone/pad-contact review.

Run with analysis/.venv/bin/python after verify_native.py. This reads native
polygons; it does not infer thermal-spoke count merely from a DRC result.
"""
from pathlib import Path
import json
from shapely.geometry import Polygon,box,LineString
from shapely.ops import unary_union
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as Patch

HERE=Path(__file__).resolve().parent
def union(rows):return unary_union([Polygon(p['shell'],p['holes']).buffer(0) for p in rows])
def parts(g):
 if g.is_empty:return []
 if g.geom_type in ['Polygon','LineString','LinearRing']:return [g]
 return [p for a in g.geoms for p in parts(a)]
def draw(ax,g,color,alpha=1):
 for p in parts(g):
  if p.geom_type!='Polygon':continue
  ax.add_patch(Patch(list(p.exterior.coords),facecolor=color,edgecolor='none',alpha=alpha))
  for h in p.interiors:ax.add_patch(Patch(list(h.coords),facecolor='white',edgecolor='none'))

def main():
 data=json.loads((HERE/'copper-native.json').read_text());result={}
 rois={'U7':box(69.2,36.4,72.4,39.2),'J20':box(60.5,83.3,62.7,85.35)}
 roi=unary_union(list(rois.values()))
 copper={k:{layer:union(v['copper'][layer]) for layer in ['F.Cu','B.Cu']} for k,v in data.items()}
 for layer in ['F.Cu','B.Cu']:
  before,after=[copper[k][layer] for k in ['baseline','candidate']]
  add=after.difference(before);remove=before.difference(after);xor=add.union(remove)
  outside=xor.difference(roi)
  # KiCad's integer-polygon intersection/union can move an unchanged edge
  # by a native internal unit. Keep the raw XOR, and independently bound
  # only its out-of-ROI residue by a 2 nm (0.000002 mm) boundary buffer.
  quantization_mm=.000002
  bounded=after.difference(before.buffer(quantization_mm)).union(before.difference(after.buffer(quantization_mm))).difference(roi)
  assert bounded.area<1e-12,('Copper changed outside reviewed neighborhoods beyond 2 nm',layer,bounded.area,bounded.bounds)
  if layer=='B.Cu':assert xor.area<1e-8,('Back copper changed',xor.area)
  result[layer]=dict(before_mm2=before.area,after_mm2=after.area,added_mm2=add.area,removed_mm2=remove.area,
                     changed_bounds_mm=list(xor.bounds) if not xor.is_empty else [],outside_roi_area_mm2=outside.area,
                     outside_roi_residue_after_2nm_boundary_buffer_mm2=bounded.area,boundary_tolerance_mm=quantization_mm,
                     reviewed_roi_bounds_mm={name:list(region.bounds) for name,region in rois.items()},
                     roi_areas={name:dict(added_mm2=add.intersection(region).area,removed_mm2=remove.intersection(region).area) for name,region in rois.items()})
 body=box(69.548,36.807,71.548,38.807);interior=box(69.848,37.107,71.248,38.507)
 contact={}
 for label,v in data.items():
  zone=union(v['front_zone']);contact[label]={}
  for name,p in v['pads'].items():
   if p['net']!='GND':continue
   pad=union(p['polygons']);rings={}
   for offset in [.01,.025,.05]:
    contour=pad.buffer(offset,resolution=32).boundary
    segments=[s for s in parts(zone.intersection(contour)) if s.length>1e-6]
    rings[str(offset)]=dict(zone_contact_segment_count=len(segments),segment_lengths_mm=[s.length for s in segments],total_contact_length_mm=sum(s.length for s in segments))
   contact[label][name]=dict(pad_area_mm2=pad.area,zone_overlap_pad_area_mm2=zone.intersection(pad).area,offset_contours=rings)
  result[label+'_U7_body']=dict(total_FCu_under_nominal_body_mm2=copper[label]['F.Cu'].intersection(body).area,
                               total_FCu_under_central_1p4mm_square_mm2=copper[label]['F.Cu'].intersection(interior).area,
                               zone_Cu_under_nominal_body_mm2=zone.intersection(body).area,
                               zone_Cu_under_central_1p4mm_square_mm2=zone.intersection(interior).area)
 result['zone_contact_geometry']=contact
 result['interpretation']='Offset-contour contacts measure actual zone touch, separately from fixed pads/traces. Counts need geometric interpretation; they are not automatically KiCad relief-spoke counts. Body areas are geometry, not a temperature/reflow model. Raw full-copper XOR is reported even where tiny remote boundary slivers are contained within the independently checked 2 nm native-polygon rounding tolerance.'
 (HERE/'copper-verification.json').write_text(json.dumps(result,indent=2)+'\n')
 fig,axes=plt.subplots(1,2,figsize=(12,6),layout='constrained')
 for ax,(label,v) in zip(axes,data.items()):
  draw(ax,copper[label]['F.Cu'].intersection(rois['U7']),'#bcc6d0')
  draw(ax,union(v['front_zone']).intersection(rois['U7']),'#b98619')
  for name,p in v['pads'].items():
   if not name.startswith('U7.'):continue
   draw(ax,union(p['polygons']),'#d4dbe4')
   x,y=p['at_mm'];ax.text(x,y,name.split('.')[1],fontsize=8,ha='center',va='center')
  ax.plot(*body.exterior.xy,color='#7b3fb2',linestyle='--',linewidth=1)
  ax.set(xlim=(69.2,72.4),ylim=(39.2,36.4),aspect='equal',title=label, xlabel='x (mm)',ylabel='y (mm)')
 fig.suptitle('U7 native copper: gray pads/traces; gold actual GND zone; dashed nominal body\nA visible trace connection is not evidence of two zone-relief spokes')
 fig.savefig(HERE/'U7-zone-contacts.png',dpi=180);plt.close(fig)
 print(json.dumps({k:v for k,v in result.items() if k!='zone_contact_geometry'},indent=2))

if __name__=='__main__':main()
