#!/usr/bin/env python3
"""Preserve edge/mask/copper drawing and zone policy independently of routes."""
from pathlib import Path
import argparse,hashlib,json,sys
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'analysis/v1_1_solar_attachments_20261012/review'))
import check_solar_attachments as sx
BASE_SHA='8e2f83797dd68195aa71b73fc252fe57e53ccd3683ef5f74739dc4d25d6ce8d5'
def capture(path):
    tree=sx.parse(path.read_text())
    drawings={sx.field(n,'uuid'):n for n in tree if isinstance(n,list) and n[0].startswith('gr_')}
    zones={sx.field(n,'uuid'):[c for c in n if not (isinstance(c,list) and c[0] in ['filled_polygon','filled_areas_thickness','fill_segments','island'])] for n in sx.nodes(tree,'zone')}
    return dict(pcb=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),drawings=drawings,zones=zones,setup=sx.nodes(tree,'setup'),general=sx.nodes(tree,'general'))
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--pcb',type=Path,required=True);ap.add_argument('--capture-baseline',action='store_true');a=ap.parse_args();data=capture(a.pcb)
    if a.capture_baseline:
        assert data['sha256']==BASE_SHA
        (HERE/'baseline-static-geometry.json').write_text(json.dumps(data,indent=2)+'\n');return
    old=json.loads((HERE/'baseline-static-geometry.json').read_text())
    for field in ['drawings','zones','setup','general']:assert old[field]==data[field],('Unrelated static board change',field)
    r=dict(status='PASS',baseline_sha256=old['sha256'],candidate_sha256=data['sha256'],unchanged_board_graphics=len(data['drawings']),unchanged_zone_definitions=len(data['zones']),unchanged_setup_and_general=True,note='Raw board-level primitives and zone policy match; filled polygons intentionally excluded. Component-local graphics are reviewed separately.')
    (HERE/'static-geometry-scope.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':main()
