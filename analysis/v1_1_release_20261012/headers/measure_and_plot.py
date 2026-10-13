#!/usr/bin/env python3
"""Measure exported native pad/track polygons and render the rear access comparison."""
from pathlib import Path
import gzip,json
from shapely.geometry import Polygon,Point
from shapely.ops import unary_union
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as PlotPolygon

HERE=Path(__file__).resolve().parent
def union(rows):return unary_union([Polygon(r['shell'],r['holes']).buffer(0) for r in rows])
def read(name):return json.loads(gzip.decompress((HERE/name).read_bytes()))

def main():
    baseline=read('native-audit.json.gz');candidate=read('candidate-geometry.json.gz');manifest=json.loads((HERE/'candidate.json').read_text())
    pieces=[]
    for item in candidate['items']:
        for layer,polys in item['polygons'].items():
            if layer in ['0','2'] and polys:pieces.append((item,layer,union(polys)))
    outline=union(candidate['outline']);pads={p['key']:p for p in candidate['pth']};rows=[]
    oldgeo={(p['key'],l):union(v) for p in baseline['items'] if p['kind']=='pad' for l,v in p['polygons'].items() if l in ['0','2']}
    for item,layer,g in pieces:
        if item['kind']!='pad' or not item.get('key','').startswith(('J3.','J4.')):continue
        p=pads[item['key']];hole=Point(p['at_mm']);foreign=[(q,gg) for q,ll,gg in pieces if ll==layer and q['net']!=p['net']]
        gap,near=min((g.distance(gg),q.get('key',q['uuid'])) for q,gg in foreign)
        hole_gap,hole_near=min((hole.distance(gg)-.25,q.get('key',q['uuid'])) for q,gg in foreign)
        old=oldgeo[item['key'],layer];annulus=hole.distance(g.boundary)-.25
        assert gap>=.1-.0002,(item['key'],layer,'copper gap',gap,near)
        assert hole_gap>=.28-.0002,(item['key'],layer,'drill-to-copper gap',hole_gap,hole_near)
        assert annulus>=.19-.0002,(item['key'],layer,'annulus',annulus)
        assert g.distance(outline.boundary)>=.2-.0002
        if layer=='0':assert g.equals(old),('Front pad changed',item['key'])
        rows.append(dict(key=item['key'],layer=layer,nominal_minimum_annulus_mm=.19,native_polygon_annulus_mm=annulus,copper_area_mm2=g.area,previous_area_mm2=old.area,
          land_area_gain_percent=(g.area/old.area-1)*100,exposed_land_excluding_drill_gain_percent=((g.area-3.141592653589793*.25**2)/(old.area-3.141592653589793*.25**2)-1)*100,
          min_foreign_copper_gap_mm=gap,nearest_foreign_item=near,min_hole_to_foreign_copper_mm=hole_gap,hole_nearest_foreign_item=hole_near,min_pad_to_outline_mm=g.distance(outline.boundary)))
    changed={r['uuid'] for r in manifest['route_changes']+manifest['added_routes']};routes=[]
    for item,layer,g in pieces:
        if item['uuid'] not in changed:continue
        foreign=[(q,gg) for q,ll,gg in pieces if ll==layer and q['net']!=item['net']]
        gap,near=min((g.distance(gg),q.get('key',q['uuid'])) for q,gg in foreign)
        assert gap>=.1-.0002,(item['uuid'],'track gap',gap,near)
        routes.append(dict(uuid=item['uuid'],net=item['net'],layer=layer,min_foreign_copper_gap_mm=gap,nearest_foreign_item=near,min_copper_to_outline_mm=g.distance(outline.boundary)))
    back=[r for r in rows if r['layer']=='2']
    result=dict(header_pads=rows,altered_tracks=routes,back_min_copper_gap_mm=min(r['min_foreign_copper_gap_mm'] for r in back),back_min_hole_to_foreign_copper_mm=min(r['min_hole_to_foreign_copper_mm'] for r in back),back_min_pad_to_outline_mm=min(r['min_pad_to_outline_mm'] for r in back),changed_track_min_gap_mm=min(r['min_foreign_copper_gap_mm'] for r in routes),added_rear_land_area_mm2=sum(r['copper_area_mm2']-r['previous_area_mm2'] for r in back))
    result['upper_bound_added_copper_mass_g']=result['added_rear_land_area_mm2']*.035*8.96/1000
    (HERE/'geometry-review.json').write_text(json.dumps(result,indent=2)+'\n')
    colors={'GND':'#cbd5df','PB5':'#ee8a34','PB2':'#9934cd','RX':'#d63367','TX':'#029dad','+3.3V':'#825629','PA9':'#306fe9','PA1':'#36a17d'}
    fig,axs=plt.subplots(1,4,figsize=(15,10),facecolor='white')
    for ax,ref,label,data in zip(axs,['J3','J3','J4','J4'],['Before','After','Before','After'],[baseline,candidate,baseline,candidate]):
        for item in data['items']:
            if item['kind']=='zone':continue
            for r in item['polygons'].get('2',[]):ax.add_patch(PlotPolygon(r['shell'],facecolor=colors.get(item['net'],'#898989'),edgecolor='none',alpha=.95))
        for p in data['pth']:
            if not p['key'].startswith(ref+'.'):continue
            x,y=p['at_mm'];ax.add_patch(plt.Circle((x,y),.25,color='white'));ax.text(x,y,p['key'].split('.')[1],fontsize=9,ha='center',va='center')
        ax.set(xlim=(53.1,56.65) if ref=='J3' else (73.5,76.8),ylim=(76,68.3),title=ref+' — '+label+' (B.Cu)')
        ax.set_aspect('equal');ax.grid(alpha=.15)
    fig.suptitle('Programming headers: enlarged rear tack lands, existing holes and front lands retained',fontsize=13)
    fig.text(.5,.025,'Coordinate view of native copper polygons. Pads: 0.88 mm front; 1.20 × 0.88 mm back, shifted 0.12 mm inward. Holes: 0.50 mm.\nPB5 moves 0.04 mm; RX receives a short dogleg. Ground fill omitted here to show solder lands and route spacing.',ha='center',fontsize=11)
    fig.tight_layout(rect=[0,.07,1,.96]);fig.savefig(HERE/'header-back-before-after.png',dpi=170)
    print(json.dumps({k:v for k,v in result.items() if k not in ['header_pads','altered_tracks']},indent=2))

if __name__=='__main__':main()
