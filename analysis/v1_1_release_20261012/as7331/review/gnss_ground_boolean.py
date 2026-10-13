#!/usr/bin/env python3
"""Exact native polygon-set difference of filled rear GND in the GNSS ROI."""
from pathlib import Path
import json,hashlib
import pcbnew,wx
HERE=Path(__file__).resolve().parent
SCRATCH=Path.home()/'Repositories/ai-working/scratch/stratolink-release-20261012/as7331/review'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(name):
    path=SCRATCH/('refill-'+name)/'stratolink.kicad_pcb'
    manifest=json.loads((path.parent/'manifest.json').read_text())
    assert sha(path)==manifest['refilled_pcb_sha256']
    board=pcbnew.LoadBoard(str(path));union=pcbnew.SHAPE_POLY_SET()
    for z in board.Zones():
        if z.GetNetname()=='GND' and not z.GetIsRuleArea() and z.IsOnLayer(pcbnew.B_Cu):union.BooleanAdd(z.GetFilledPolysList(pcbnew.B_Cu))
    roi=pcbnew.SHAPE_POLY_SET();roi.NewOutline()
    for x,y in [(59,33),(64,33),(64,46),(59,46)]:roi.Append(round(x*1e6),round(y*1e6))
    union.BooleanIntersection(roi)
    return union,manifest
def polys(p):
    return [[[p.Outline(i).CPoint(j).x/1e6,p.Outline(i).CPoint(j).y/1e6] for j in range(p.Outline(i).PointCount())] for i in range(p.OutlineCount())]
def main():
    app=wx.App(False);old,om=load('baseline');new,nm=load('candidate')
    lost=pcbnew.SHAPE_POLY_SET();lost.BooleanSubtract(old,new)
    gained=pcbnew.SHAPE_POLY_SET();gained.BooleanSubtract(new,old)
    boundary_screen=[]
    for um in [1,2,5,10]:
        expanded=pcbnew.SHAPE_POLY_SET();expanded.BooleanAdd(new)
        expanded.Inflate(um*1000,pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS,10,True)
        beyond=pcbnew.SHAPE_POLY_SET();beyond.BooleanSubtract(old,expanded)
        boundary_screen.append(dict(expansion_um=um,remaining_lost_area_mm2=beyond.Area()/1e12))
    r=dict(status='NO_LOST_FILLED_GROUND' if abs(lost.Area())<1 else 'LOST_GROUND_REQUIRES_REVIEW',baseline_source_sha256=om['source_hashes']['stratolink.kicad_pcb'],candidate_source_sha256=nm['source_hashes']['stratolink.kicad_pcb'],roi_mm=[59,33,64,46],baseline_area_mm2=old.Area()/1e12,candidate_area_mm2=new.Area()/1e12,lost_area_mm2=lost.Area()/1e12,gained_area_mm2=gained.Area()/1e12,lost_polygons_mm=polys(lost),gained_polygons_mm=polys(gained),scope='KiCad integer polygon Boolean of CLI-saved filled B.Cu GND only; not an RF field solver. Mask dielectric and antenna matching require measurement.')
    r['loss_boundary_distance_screen']=boundary_screen
    (HERE/'gnss-ground-boolean.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if 'polygons' not in k},indent=2))
if __name__=='__main__':main()
