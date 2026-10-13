#!/usr/bin/env python3
"""Compare unioned native copper and filled GND before/after zone cleanup."""
from pathlib import Path
import json,gzip
from shapely.geometry import Polygon
from shapely.ops import unary_union
HERE=Path(__file__).resolve().parent
data=json.loads(gzip.decompress((HERE/'native_geometry.json.gz').read_bytes()))
def union(contours):return unary_union([Polygon(c['shell'],c['holes']) for c in contours])
def ground(d,layer):return unary_union([union(z['fill'].get(layer,[])) for z in d['zones'] if z['net']=='GND'])
def compare(a,b):
 added=b.difference(a);removed=a.difference(b)
 return dict(before_area_mm2=a.area,after_area_mm2=b.area,added_area_mm2=added.area,removed_area_mm2=removed.area,symmetric_difference_area_mm2=a.symmetric_difference(b).area,exact_geometric_equality=a.equals(b),added_bounds_mm=list(added.bounds) if not added.is_empty else None,removed_bounds_mm=list(removed.bounds) if not removed.is_empty else None)
result={}
for variant in ['front-only-main','single-two-layer']:
 result[variant]={}
 for layer in ['F.Cu','B.Cu']:
  row=compare(union(data['baseline']['copper'][layer]),union(data[variant]['copper'][layer]))
  row['GND_fill_only']=compare(ground(data['baseline'],layer),ground(data[variant],layer))
  assert row['exact_geometric_equality'] and row['GND_fill_only']['exact_geometric_equality']
  result[variant][layer]=row
(HERE/'copper-comparison.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
