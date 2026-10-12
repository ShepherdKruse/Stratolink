#!/usr/bin/env python3
"""Compare an explicitly extracted candidate to the frozen baseline sweep.

Run with analysis/.venv/bin/python. Never changes baseline artifacts or CAD.
"""
from pathlib import Path
import argparse
import hashlib
import json

from model import measure_geometry, mass_components, FR4_DENSITIES

HERE = Path(__file__).resolve().parent


def summarize(data):
    edge, outer, laminate, copper, barrels = measure_geometry(data)
    thickness = data['board_thickness_mm']
    copper_area = sum(p.area for p in copper.values())
    parts = mass_components(laminate.area, copper_area, barrels, thickness)
    return {'source_sha256':data['source_sha256'], 'board_thickness_mm':thickness,
            'outside_area_mm2':outer.area, 'outline_net_area_mm2':edge.area,
            'laminate_net_area_mm2':laminate.area,
            'copper_area_mm2':{name:p.area for name,p in copper.items()},
            'drill_holes_count':len(data['drills']),
            'mass_g_nominal':sum(parts),
            'mass_g_density_range':[sum(mass_components(laminate.area,copper_area,barrels,thickness,d)) for d in (FR4_DENSITIES[0],FR4_DENSITIES[-1])],
            'mass_parts_g':dict(zip(['core','planar_copper','mask','barrel_density_correction'],parts))}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--geometry',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    baseline=json.loads((HERE/'geometry_native.json').read_text())
    candidate=json.loads(args.geometry.read_text())
    original_candidate=Path(candidate['candidate_source_path'])
    assert hashlib.sha256(original_candidate.read_bytes()).hexdigest()==candidate['source_sha256'], 'Candidate no longer matches extracted geometry'
    b,c=summarize(baseline),summarize(candidate)
    result={'baseline':b,'candidate':c,'delta_g':c['mass_g_nominal']-b['mass_g_nominal'],
            'delta_mg':1000*(c['mass_g_nominal']-b['mass_g_nominal']),
            'delta_parts_g':{k:c['mass_parts_g'][k]-v for k,v in b['mass_parts_g'].items()},
            'method':'Native KiCad copper/outline after hole subtraction; identical model.py material assumptions; no finish/solder/components/panel attachment added',
            'source_geometry':str(args.geometry.resolve())}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
