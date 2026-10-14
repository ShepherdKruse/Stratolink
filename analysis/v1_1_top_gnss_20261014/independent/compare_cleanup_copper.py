#!/usr/bin/env python3
"""Read-only full filled-copper delta; do not equate a small source patch to a small fill change."""
from pathlib import Path
import argparse,hashlib,json
from shapely.geometry import Polygon
from shapely.ops import unary_union
p=argparse.ArgumentParser(description=__doc__)
for n in ['before','after','output']:p.add_argument('--'+n,type=Path,required=True)
a=p.parse_args();assert not a.output.exists()
ds=[json.loads(p.read_text())for p in [a.before,a.after]]
def load(rows):return unary_union([Polygon(x['shell'],x['holes'])for x in rows])
def parts(g):return[g]if g.geom_type=='Polygon'else[x for x in g.geoms if x.geom_type=='Polygon']
r={'before_pcb_sha256':ds[0]['sha256'],'pcb_sha256':ds[1]['sha256'],'input_sha256':{'before':hashlib.sha256(a.before.read_bytes()).hexdigest(),'after':hashlib.sha256(a.after.read_bytes()).hexdigest()},'layers':{},'limits':['Includes saved-fill changes caused by the new solid-zone boundary retreat and restoration of inherited thermal/minimum-fill behavior.','All nonzero components are retained, including numerical polygon seams. This is a quantitative delta, not an independent authorization for every copper change. See native scope and final reference/thermal reports.']}
for layer in ['F.Cu','B.Cu']:
 old,new=[load(d['copper'][layer])for d in ds];row={}
 for label,g in [('added',new.difference(old)),('removed',old.difference(new))]:
  row[label]={'area_mm2':g.area,'parts':[{'area_mm2':q.area,'bounds_mm':list(q.bounds)}for q in parts(g)]}
 r['layers'][layer]=row
a.output.write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps({l:{k:v['area_mm2']for k,v in d.items()}for l,d in r['layers'].items()},indent=2))
