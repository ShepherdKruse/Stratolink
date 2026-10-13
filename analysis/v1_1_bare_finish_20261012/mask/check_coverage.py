#!/usr/bin/env python3
"""Check native and actual Gerber openings; run with analysis/.venv Python."""
from pathlib import Path
import gzip,json,re,zipfile
from shapely.geometry import Polygon,box
from shapely.ops import unary_union

HERE=Path(__file__).resolve().parent
OUT=Path.home()/'Repositories/ai-working/scratch/stratolink-bare-finish-20261012/mask'

def union(rows):return unary_union([Polygon(r['shell'],r['holes']).buffer(0) for r in rows])

def main():
    data=json.loads(gzip.decompress((HERE/'native-geometry.json.gz').read_bytes()))
    expected=box(52,28,78,88);board=union(data['candidate']['board'])
    result={}
    for face,mask,cu,suffix in [('front','F.Mask','F.Cu','gts'),('back','B.Mask','B.Cu','gbs')]:
        native=union(data['candidate'][mask]);copper=union(data['candidate'][cu])
        assert native.equals(expected)
        assert board.difference(native).area==0
        assert copper.difference(native).area==0
        path=OUT/'candidate-exports'/('stratolink-'+mask.replace('.','_')+'.'+suffix)
        text=path.read_text()
        assert '%TF.FilePolarity,Negative*%' in text
        assert '%FSLAX46Y46*%' in text and '%MOMM*%' in text and '%LPD*%' in text
        assert '%LPC*%' not in text,'Any clear plot operation requires full Gerber boolean evaluation'
        region=re.search(r'G36\*\n(.*?)G37\*',text,re.S).group(1)
        vertices=[]
        for line in region.splitlines():
            m=re.fullmatch(r'X(-?\d+)Y(-?\d+)D0[12]\*',line)
            if m:vertices.append((int(m[1])/1e6,-int(m[2])/1e6))
        plotted=Polygon(vertices)
        assert plotted.equals(expected),'First exported solid region must be the full opening'
        assert board.difference(plotted).area==0 and copper.difference(plotted).area==0
        result[face]=dict(opening_bounds_mm=list(native.bounds),opening_area_mm2=native.area,
          board_projected_area_mm2=board.area,covered_board_area_mm2=board.difference(native).area,
          copper_area_mm2=copper.area,covered_copper_area_mm2=copper.difference(native).area,
          board_to_opening_boundary_min_mm=board.distance(native.boundary),
          copper_islands=len(data['candidate'][cu]),every_native_island_exposed=True,
          actual_gerber_negative_file_polarity=True,actual_gerber_full_rectangle_region=True,
          actual_gerber_has_no_clear_plot_operation=True,actual_gerber_mask=str(path))
    job=json.loads((OUT/'candidate-exports/stratolink-job.gbrjob').read_text())
    mask_layers=[r for r in job['MaterialStackup'] if r['Type']=='SolderMask']
    assert len(mask_layers)==2 and all(r['Thickness']==0 for r in mask_layers)
    assert job['GeneralSpecs']['BoardThickness']==.4
    result['stackup']=dict(board_mm=.4,mask_layers_mm=[r['Thickness'] for r in mask_layers],core_mm=.33)
    result['interpretation']='The Gerber FilePolarity Negative designation identifies mask openings. Its dark full-board region removes mask over both faces. Blank mask files would not communicate this.'
    (HERE/'coverage.json').write_text(json.dumps(result,indent=2)+'\n')
    old_mask=union(data['baseline']['F.Mask']);front_copper=union(data['candidate']['F.Cu'])
    pads=[(p,union(p['polygons'])) for p in data['silkscreen']['pads']]
    labels=[]
    for t in data['silkscreen']['texts']:
        text=union(t['polygons']);nearest=min(pads,key=lambda x:text.distance(x[1]));p=nearest[0]
        row=dict(text=t['text'],uuid=t['uuid'],distance_to_old_mask_opening_mm=text.distance(old_mask),
          area_on_old_mask_openings_mm2=text.intersection(old_mask).area,nearest_copper_pad=p['ref']+'.'+p['number'],
          distance_to_copper_pad_mm=text.distance(nearest[1]),area_on_copper_pads_mm2=sum(text.intersection(g).area for _,g in pads),
          area_on_copper_mm2=text.intersection(front_copper).area)
        assert row['area_on_copper_pads_mm2']==0 and row['area_on_old_mask_openings_mm2']==0
        labels.append(row)
    (HERE/'silkscreen-review.json').write_text(json.dumps(labels,indent=2)+'\n')
    with zipfile.ZipFile(HERE/'mask-gerbers.zip','w',compression=zipfile.ZIP_DEFLATED) as archive:
        for pattern in ['*.gts','*.gbs','*.gbrjob']:
            for p in (OUT/'candidate-exports').glob(pattern):archive.write(p,p.name)
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
