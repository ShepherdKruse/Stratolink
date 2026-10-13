#!/usr/bin/env python3
"""Adversarial actual-export fixtures for the green finish gate."""
from pathlib import Path
import importlib.util,json,sys,tempfile,shutil,hashlib
import pcbnew,wx
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
GEN=ROOT/'analysis/v1_1_release_20261012/manufacturing/generate.py'
BASE=Path('/Users/twarn/Repositories/ai-working/scratch/stratolink-release-20261012/as7331')

def main():
    spec=importlib.util.spec_from_file_location('gate',GEN);g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
    app=wx.App(False);good=BASE/'green-mask-trial3/stratolink.kicad_pcb';bad=BASE/'green-gate-negative1/stratolink.kicad_pcb'
    artifacts=BASE/'finish-artwork-trial3';badart=BASE/'green-gate-negative1/gerbers';board=pcbnew.LoadBoard(str(good))
    proof=g.green_finish_proof(board,artifacts,'stratolink');rejected={}
    def negative(name,fn):
        try:fn()
        except ValueError as e:rejected[name]=str(e)
        else:raise AssertionError('Unsafe finish accepted: '+name)
    negative('native_full_board_opening',lambda:g.green_finish_proof(pcbnew.LoadBoard(str(bad)),badart,'stratolink'))
    # Use the valid native board with actual invalid plotted mask: this reaches
    # the separate Gerber test, rather than passing on the native test alone.
    negative('polygonized_Gerber_full_board_opening',lambda:g.green_finish_proof(board,badart,'stratolink'))
    with tempfile.TemporaryDirectory(prefix='green-gate-',dir=BASE) as temp:
        temp=Path(temp)
        for p in artifacts.iterdir():shutil.copy2(p,temp/p.name)
        path=temp/'stratolink-F_Mask.gts';original=path.read_text()
        negative('clear_polarity',lambda:g.selective_mask_regions(original+'\n%LPC*%\n'))
        negative('unexpected_flash',lambda:g.selective_mask_regions(original.replace('M02*','X0Y0D03*\nM02*')))
        negative('unexpected_arc',lambda:g.selective_mask_regions(original.replace('G01*','G02*',1)))
        negative('unclosed_region',lambda:g.selective_mask_regions(original.replace('G37*','',1)))
        header=original.split('G36*',1)[0]
        path.write_text(header+'G36*\nX0Y0D02*\nX100000Y0D01*\nX100000Y100000D01*\nX0Y0D01*\nG37*\nM02*\n')
        negative('solar_pad_covered_in_actual_Gerber',lambda:g.green_finish_proof(board,temp,'stratolink'))
        path.write_text(original)
        jobpath=temp/'stratolink-job.gbrjob';job=json.loads(jobpath.read_text())
        for item in job['MaterialStackup']:
            if item['Type']=='SolderMask':item['Color']='Black'
        jobpath.write_text(json.dumps(job));negative('wrong_mask_color',lambda:g.green_finish_proof(board,temp,'stratolink'))
        jobpath.write_bytes((artifacts/jobpath.name).read_bytes())
        silk=temp/'stratolink-F_Silkscreen.gto';silk.write_text(silk.read_text().replace('M02*','G36*\nX0Y0D02*\nX1Y1D01*\nG37*\nM02*'))
        negative('nonempty_silk_Gerber',lambda:g.green_finish_proof(board,temp,'stratolink'))
    # Independent geometry fixtures test nested contour holes and arbitrary
    # oblique boundaries, not only the old axis-aligned rectangle.
    outer=[(-2,-2),(2,-2),(2,2),(-2,2)];hole=[(-1,-1),(1,-1),(1,1),(-1,1)]
    assert not g.mask_region_contains((0,0),[outer,hole]);assert g.mask_region_contains((1.5,0),[outer,hole])
    assert g.polygon_contains((0,0),[(-2,0),(0,-2),(2,0),(0,2)])
    report={'generator_sha256':g.sha(GEN),'positive_fixture':str(good),'positive_mask_regions':{s:proof[s]['polygon_regions'] for s in ['F','B']},
      'negative_fixtures_rejected':rejected,'nested_contour_and_oblique_geometry_checked':True,
      'native_and_Gerber_full_face_regression_both_rejected':True}
    (HERE/'green-gate-test.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
