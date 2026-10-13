#!/usr/bin/env python3
"""Verify the mask-only candidate with KiCad's Python API and native exporters."""
from pathlib import Path
from collections import Counter
import gzip,hashlib,json,subprocess,sys
import pcbnew,wx

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
OUT=Path.home()/'Repositories/ai-working/scratch/stratolink-bare-finish-20261012/mask'
CLI='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
sys.path.insert(0,str(ROOT/'analysis/v1_1_ground_20261012/review'))
from verify_native import contours,normplot,physical_set,pads

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(args,log):
    result=subprocess.run(args,check=True,text=True,capture_output=True)
    log.write_text(result.stdout+result.stderr)

def main():
    manifest=json.loads((HERE/'candidate.json').read_text())
    app=wx.App(False)
    boards={label:pcbnew.LoadBoard(str(OUT/label/'stratolink.kicad_pcb')) for label in ['baseline','candidate']}
    for b in boards.values():b.BuildConnectivity()
    old,new=[pads(boards[k]) for k in ['baseline','candidate']]
    assert old.keys()==new.keys() and len(new)==232
    for uid,p in new.items():
        assert p.GetNetname()==old[uid].GetNetname()
        assert physical_set(boards['baseline'].GetConnectivity(),old[uid])==physical_set(boards['candidate'].GetConnectivity(),p)
    assert boards['candidate'].GetConnectivity().GetUnconnectedCount(False)==0
    native={}
    for label,b in boards.items():
        native[label]={}
        for layer in [pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.F_Mask,pcbnew.B_Mask]:
            poly=pcbnew.SHAPE_POLY_SET();b.ConvertBrdLayerToPolygonalContours(layer,poly);poly.Simplify()
            native[label][b.GetLayerName(layer)]=contours(poly)
        outline=pcbnew.SHAPE_POLY_SET();assert b.GetBoardPolygonOutlines(outline,False)
        native[label]['board']=contours(outline)
    for layer in ['F.Cu','B.Cu']:assert native['baseline'][layer]==native['candidate'][layer],layer
    native['silkscreen']={'texts':[],'pads':[]}
    for t in boards['candidate'].GetDrawings():
        if t.GetLayer()!=pcbnew.F_SilkS or not isinstance(t,pcbnew.PCB_TEXT):continue
        p=pcbnew.SHAPE_POLY_SET();t.TransformTextToPolySet(p,0,100,pcbnew.ERROR_OUTSIDE)
        native['silkscreen']['texts'].append(dict(text=t.GetText(),uuid=t.m_Uuid.AsString(),polygons=contours(p)))
    for f in boards['candidate'].GetFootprints():
        for t in f.Pads():
            if not t.IsOnLayer(pcbnew.F_Cu):continue
            p=pcbnew.SHAPE_POLY_SET();t.TransformShapeToPolygon(p,pcbnew.F_Cu,0,100,pcbnew.ERROR_OUTSIDE)
            native['silkscreen']['pads'].append(dict(ref=f.GetReference(),number=t.GetNumber(),uuid=t.m_Uuid.AsString(),polygons=contours(p)))
    (HERE/'native-geometry.json.gz').write_bytes(gzip.compress((json.dumps(native,separators=(',',':'))+'\n').encode(),mtime=0))
    exports={};drc={}
    for label in ['baseline','candidate']:
        pcb=OUT/label/'stratolink.kicad_pcb'
        target=OUT/(label+'-exports');target.mkdir(exist_ok=True);exports[label]=target
        run([CLI,'pcb','export','gerbers','--layers','F.Cu,B.Cu,F.Mask,B.Mask,F.Paste,B.Paste,Edge.Cuts','--output',str(target),str(pcb)],target/'gerber.log')
        run([CLI,'pcb','export','drill','--format','excellon','--excellon-units','mm','--excellon-separate-th','--output',str(target),str(pcb)],target/'drill.log')
        report=HERE/(label+'-drc.json')
        run([CLI,'pcb','drc','--schematic-parity','--format','json','--output',str(report),str(pcb)],target/'drc.log')
        drc[label]=json.loads(report.read_text())
    same=[];different=[]
    for a in exports['baseline'].iterdir():
        if a.suffix not in {'.gbr','.drl','.gbl','.gtl','.gbs','.gts','.gbp','.gtp','.gm1'}:continue
        b=exports['candidate']/a.name
        if normplot(a.read_text())==normplot(b.read_text()):same.append(a.name)
        else:different.append(a.name)
    assert sorted(different)==['stratolink-B_Mask.gbs','stratolink-F_Mask.gts'],different
    for label in ['baseline','candidate']:
        for n,h in manifest['baseline_hashes' if label=='baseline' else 'files'].items():
            assert sha(OUT/label/n)==h,('Source altered',label,n)
    result=dict(source_hash=manifest['files']['stratolink.kicad_pcb'],native_version=pcbnew.GetBuildVersion(),physical_pad_sets_preserved=232,
      zero_opens=True,front_and_back_native_copper_polygons_exact=True,unchanged_manufacturing_plots=sorted(same),changed_manufacturing_plots=sorted(different),
      drc={k:dict(violations=len(v['violations']),types=dict(Counter(x['type'] for x in v['violations'])),unconnected=len(v['unconnected_items']),parity=len(v['schematic_parity'])) for k,v in drc.items()})
    (HERE/'native-verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
