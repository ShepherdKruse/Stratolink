#!/usr/bin/env python3
"""Read-only candidate fabrication review. Run using KiCad's Python.

Exports are kept outside the repository. Candidate hashes must remain unchanged.
No zone refill or save is requested by these export operations.
"""
from pathlib import Path
import argparse
import collections
import hashlib
import json
import math
import re
import subprocess
import sys

import pcbnew
import wx

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'analysis/v1_1_microphone_20261012/review'))
from check_removal import parse,nodes,field,prop


def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def run(args,log):
    r=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    log.write_text(r.stdout)
    assert r.returncode==0,(args,r.stdout)


def drill_hits(path):
    text=path.read_text()
    tool=None;diameters={};hits=[]
    for line in text.splitlines():
        m=re.fullmatch(r'T(\d+)C([\d.]+)',line)
        if m:diameters[int(m[1])]=float(m[2]);continue
        m=re.fullmatch(r'T(\d+)',line)
        if m:tool=int(m[1]);continue
        m=re.fullmatch(r'X(-?[\d.]+)Y(-?[\d.]+)',line)
        if m:hits.append({'x':float(m[1]),'y':-float(m[2]),'diameter':diameters[tool]})
    return text,hits


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',type=Path,default=Path('/Users/twarn/Repositories/ai-working/scratch/stratolink-solar-anchor/candidate'))
    parser.add_argument('--output',type=Path,default=Path('/Users/twarn/Repositories/ai-working/scratch/stratolink-solar-fab-review'))
    args=parser.parse_args()
    candidate=args.candidate.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    paths=[candidate/f'stratolink.{ext}' for ext in ['kicad_pcb','kicad_sch','kicad_pro']]
    before={p.name:digest(p) for p in paths}
    boardpath=paths[0]
    gerber=out/'gerbers';drill=out/'drills';svg=out/'svg'
    for p in [gerber,drill,svg]:p.mkdir(exist_ok=True)
    run(['kicad-cli','pcb','export','gerbers','--layers','F.Cu,B.Cu,F.Mask,B.Mask,F.Paste,B.Paste,Edge.Cuts',
         '--output',str(gerber),str(boardpath)],out/'gerbers.log')
    run(['kicad-cli','pcb','export','drill','--format','excellon','--excellon-separate-th',
         '--generate-map','--map-format','svg','--generate-report','--output',str(drill),str(boardpath)],out/'drill.log')
    run(['kicad-cli','pcb','export','svg','--layers','F.Cu,B.Cu,F.Mask,B.Mask,Edge.Cuts',
         '--mode-multi','--page-size-mode','2','--exclude-drawing-sheet','--output',str(svg),str(boardpath)],out/'svg.log')
    run(['kicad-cli','pcb','drc','--format','json','--schematic-parity','--output',str(out/'drc-readonly.json'),str(boardpath)],out/'drc.log')
    after={p.name:digest(p) for p in paths}
    assert before==after,'Candidate changed during read-only review'
    app=wx.App(False)
    board=pcbnew.LoadBoard(str(boardpath));fps={f.GetReference():f for f in board.GetFootprints()}
    tree=parse(boardpath.read_text());rawfps={prop(f,'Reference'):f for f in nodes(tree,'footprint')}
    poly=pcbnew.SHAPE_POLY_SET()
    assert board.GetBoardPolygonOutlines(poly,False,None,False,False),'Native outline did not form a valid board polygon'
    contains=lambda x,y:poly.Contains(pcbnew.VECTOR2I(pcbnew.FromMM(x),pcbnew.FromMM(y)))
    notch_checks=[]
    for side,edge,sign in [('left',53.3165,1),('right',76.6755,-1)]:
        tests=[('notch_open',edge+sign*.5,54.5,False),('upper_bank_present',edge+sign*.5,53.7,True),
               ('lower_bank_present',edge+sign*.5,55.3,True),('inside_of_notch_tip',edge+sign*1.8,54.5,True)]
        for name,x,y,expected in tests:
            actual=contains(x,y);assert actual==expected,(side,name,actual)
            notch_checks.append({'side':side,'test':name,'x':x,'y':y,'inside_board':actual})
    # Exact native footprint layers and local drills, independent of drawn appearance.
    mountpads=[]
    for ref in ['J1','J2']:
        for pad in fps[ref].Pads():
            assert not pad.IsOnLayer(pcbnew.F_Paste) and not pad.IsOnLayer(pcbnew.B_Paste),(ref,'paste layer on hand-solder pad')
            pos=pad.GetPosition();size=pad.GetDrillSize()
            row={'ref':ref,'number':pad.GetNumber(),'net':pad.GetNetname(),
                 'at_mm':[pcbnew.ToMM(pos.x),pcbnew.ToMM(pos.y)],
                 'drill_mm':[pcbnew.ToMM(size.x),pcbnew.ToMM(size.y)],
                 'pad_kind':'custom_surface_land' if size.x==0 else 'round_through_hole',
                 'drilled_hole_plated':None if size.x==0 else pad.GetAttribute()!=pcbnew.PAD_ATTRIB_NPTH,
                 'F_Cu':pad.IsOnLayer(pcbnew.F_Cu),'B_Cu':pad.IsOnLayer(pcbnew.B_Cu)}
            mountpads.append(row)
        for obj in rawfps[ref]:
            if not isinstance(obj,list):continue
            if obj[0].startswith('fp_'):assert field(obj,'layer') not in {'F.Paste','B.Paste'},(ref,'paste graphic')
    pth_file=next(drill.glob('*-PTH.drl'));npth_file=next(drill.glob('*-NPTH.drl'))
    pth_text,pth=drill_hits(pth_file);npth_text,npth=drill_hits(npth_file)
    assert 'Plated' in pth_text and 'NonPlated' in npth_text
    drilled_mounts=[p for p in mountpads if p['drill_mm'][0]>0]
    for pad in drilled_mounts:
        assert pad['drilled_hole_plated'] and pad['drill_mm'][0]==pad['drill_mm'][1]
        x,y=pad['at_mm'];d=pad['drill_mm'][0]
        assert any(abs(h['x']-x)<.00051 and abs(h['y']-y)<.00051 and abs(h['diameter']-d)<1e-5 for h in pth),('Missing mount drill',pad)
    ground_vias=[]
    for track in board.GetTracks():
        if not isinstance(track,pcbnew.PCB_VIA) or track.GetNetname()!='GND':continue
        x,y=pcbnew.ToMM(track.GetPosition().x),pcbnew.ToMM(track.GetPosition().y)
        if not (53.1<=y<=55.9 and (53.5165<=x<=55.6165 or 74.3755<=x<=76.4755)):continue
        d=pcbnew.ToMM(track.GetDrillValue())
        # KiCad's metric decimal Excellon uses 0.001 mm coordinate precision.
        assert any(abs(h['x']-x)<.00051 and abs(h['y']-y)<.00051 and abs(h['diameter']-d)<1e-5 for h in pth),('Missing ground stitching via',x,y,d)
        ground_vias.append({'uuid':track.m_Uuid.AsString(),'net':'GND','x_mm':x,'y_mm':y,'drill_mm':d})
    assert len(ground_vias)==4,('Expected two ordinary GND stitching vias per notch',ground_vias)
    # Actual slot geometry is board routing, never an oval drill request.
    assert 'G85' not in pth_text and 'G85' not in npth_text,'Unexpected Excellon slot command; inspect before release'
    for h in pth+npth:
        assert not (53.3165<h['x']<54.8165 and 54<h['y']<55),('Drill intrudes left open notch',h)
        assert not (75.1755<h['x']<76.6755 and 54<h['y']<55),('Drill intrudes right open notch',h)
    files={p.name:p for p in gerber.iterdir() if p.is_file()}
    pastefiles=[p for p in files.values() if p.suffix in {'.gtp','.gbp'} or 'Paste' in p.name]
    assert len(pastefiles)==2
    for path in pastefiles:
        txt=path.read_text()
        for ref in ['J1','J2']:
            assert not re.search(r'%TO\.(?:C,'+ref+r'\*|P,'+ref+r',)',txt),('Mount appears in exported paste',path.name,ref)
    edgefile=next(p for p in files.values() if p.suffix=='.gm1' or 'Edge_Cuts' in p.name or 'Edge.Cuts' in p.name)
    edge_text=edgefile.read_text()
    assert '%TF.FileFunction,Profile,NP*%' in edge_text,'Outline is not identified as non-plated profile'
    exported_notch_arcs=['X54316500Y-55000000I0J-500000D01*','X75675500Y-54000000I0J500000D01*']
    assert all(line in edge_text for line in exported_notch_arcs),'Expected R0.5 notch profile arcs missing from Gerber'
    drc=json.loads((out/'drc-readonly.json').read_text())
    mount_uuids={f.m_Uuid.AsString() for r,f in fps.items() if r in {'J1','J2'}}
    mount_courtyard=[v for v in drc['violations'] if 'courtyard' in v['type'] and
                    any(i.get('uuid') in mount_uuids or re.search(r'\bJ[12]\b',i.get('description','')) for i in v.get('items',[]))]
    assert not mount_courtyard,('Mount courtyard findings',mount_courtyard)
    assert not drc['unconnected_items'],'Unconnected copper remains'
    # PTH-inside-courtyard checks are disabled in the inherited project. Check
    # new round mount pads explicitly against native front/back courtyard areas.
    direct_courtyard_hits=[]
    for ref in ['J1','J2']:
        for pad in fps[ref].Pads():
            if pad.GetDrillSize().x<=0:continue
            radius=max(pad.GetSize().x,pad.GetSize().y)//2
            for other,footprint in fps.items():
                if other==ref:continue
                footprint.BuildCourtyardCaches()
                for layer in [pcbnew.F_CrtYd,pcbnew.B_CrtYd]:
                    courtyard=footprint.GetCourtyard(layer)
                    if courtyard.OutlineCount() and courtyard.Collide(pad.GetPosition(),radius):
                        direct_courtyard_hits.append({'mount':ref,'pad':pad.GetNumber(),'other':other,'layer':board.GetLayerName(layer)})
    assert not direct_courtyard_hits,('New mount pad overlaps another native courtyard',direct_courtyard_hits)
    def bbox(item):
        bb=item.GetBoundingBox()
        return [pcbnew.ToMM(v) for v in [bb.GetX(),bb.GetY(),bb.GetRight(),bb.GetBottom()]]
    def gap(a,b):
        dx=max(a[0]-b[2],b[0]-a[2],0);dy=max(a[1]-b[3],b[1]-a[3],0)
        return math.hypot(dx,dy)
    nearby=[]
    for ref,layer in [('C5',pcbnew.B_Fab),('C5',pcbnew.B_CrtYd),('U4',pcbnew.F_Fab),('U4',pcbnew.F_CrtYd)]:
        graphics=[g for g in fps[ref].GraphicalItems() if isinstance(g,pcbnew.PCB_SHAPE) and g.GetLayer()==layer]
        boxes=[bbox(g) for g in graphics];assert boxes
        extent=[min(v[0] for v in boxes),min(v[1] for v in boxes),max(v[2] for v in boxes),max(v[3] for v in boxes)]
        for anchor in ['J1','J2']:
            gb=[bbox(p) for p in fps[anchor].Pads() if p.GetNetname()=='GND']
            nearest=min(gap(g,extent) for g in gb)
            nearby.append({'anchor':anchor,'component':ref,'layer':board.GetLayerName(layer),
                           'component_drawing_extent_mm':extent,'min_ground_pad_bbox_gap_mm':nearest,
                           'interpretation':'2D pad-to-drawing bounding-box screen, includes drawn stroke; external panel/solder/wire not represented'})
    result={'status':'pass','kicad_version':pcbnew.GetBuildVersion(),'candidate':str(candidate),
            'source_sha256':before,'candidate_unchanged_by_review':True,
            'outline_count':poly.OutlineCount(),'native_notch_inside_outside_checks':notch_checks,
            'notch_wall_plated':False,
            'open_notch_file':str(edgefile),'new_mount_pads':mountpads,
            'exact_notch_arc_commands_in_nonplated_profile':exported_notch_arcs,
            'PTH_hit_count':len(pth),'NPTH_hit_count':len(npth),
            'mount_drills_matched_to_PTH_export':len(drilled_mounts),
            'ground_stitching_vias_matched_to_PTH_export':ground_vias,
            'Excellon_coordinate_match_tolerance_mm':.00051,
            'nearby_component_drawing_screen':nearby,
            'excellon_slot_commands':0,'mount_paste_apertures':0,'mount_courtyard_findings':mount_courtyard,
            'explicit_new_mount_drilled_pad_courtyard_hits':direct_courtyard_hits,
            'unconnected_items':len(drc['unconnected_items']),
            'native_drc_violation_types':dict(collections.Counter(v['type'] for v in drc['violations'])),
            'native_drc_severities':dict(collections.Counter(v['severity'] for v in drc['violations'])),
            'schematic_parity_count':len(drc.get('schematic_parity',[])),
            'export_sha256':{str(p.relative_to(out)):digest(p) for folder in [gerber,drill,svg] for p in folder.iterdir() if p.is_file()},
            'limitations':'Fit, terminal wetting, load retention and assembled clearances require the physical mockup. Existing DRC findings require separate baseline comparison; this script does not waive them.'}
    (HERE/'evidence.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
