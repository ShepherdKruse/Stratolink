#!/usr/bin/env python3
"""Conservative solar-model bounding-box screen for the proposed U6 aperture.

This is geometric occlusion only, not full ray tracing or an optical instrument
validation. It imports the existing generator without writing its model files.
"""
from pathlib import Path
import hashlib,importlib.util,json,math
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
SOURCE=ROOT/'hardware/pcb/3d/solar/generate.py'
spec=importlib.util.spec_from_file_location('existing_solar_model',SOURCE);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
native=json.loads((HERE/'candidate-native.json').read_text());xy=tuple(native['footprints']['U6']['at']);filter_z=.2+1.09-.345
rows=[]
for side,sign,edge,positive in [('left',-1,53.3165,54.8),('right',1,76.6755,75.2)]:
    mesh,_=m.build(sign,positive-edge)
    for name,vertices,faces,material in mesh.parts:
        points=[(edge+x,54.5+y,z) for x,y,z in vertices]
        bounds=[(min(v[i] for v in points),max(v[i] for v in points)) for i in range(3)]
        radial=math.sqrt(sum(max(lo-(xy[i]+.34),0,(xy[i]-.34)-hi)**2 for i,(lo,hi) in enumerate(bounds[:2])))
        height=max(0,bounds[2][1]-filter_z)
        theta=math.degrees(math.atan2(radial,height)) if height>0 else 90.
        rows.append(dict(side=side,part=name,world_bbox_mm=bounds,minimum_planar_distance_mm=radial,maximum_above_filter_mm=height,conservative_minimum_incidence_degrees=theta,clear_of_10deg_cone=theta>10))
result=dict(purpose='Geometric lower-angle bound for existing illustrative solar geometry, not optical or structural qualification',source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),candidate_pcb_sha256=native['hashes']['stratolink.kicad_pcb'],u6_candidate_xy_mm=xy,filter_z_above_board_midplane_mm=filter_z,active_area_half_width_mm=.34,filter_z_assumptions='0.4mm PCB,1.09mm nominal packageheight,0.345mm dierecess; solderstandoffnotmodeled',all_existing_solar_parts_clear_of_10_degree_normal_cone=all(r['clear_of_10deg_cone'] for r in rows),minimum_lower_bound_degrees=min(r['conservative_minimum_incidence_degrees'] for r in rows),part_bounds=rows,limitations=['Current panel/lead CAD is photo-scaled and has unmeasured real bends/thickness/wire placements.','Does not include future aperture/diffuser, actual suspension strings or clouds.','An unobstructed ±10degree cone is not proof that illumination outside that cone is rejected; an appropriate optical collector is still required.','Does not establish sunlight out-of-band rejection or UV calibration.'])
(HERE/'optical-envelope.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='part_bounds'},indent=2))
