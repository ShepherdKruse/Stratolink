#!/usr/bin/env python3
"""Rebuild only scratch electrical candidate from the protected pre-ECO source.

Requires KiCad's bundled Python, the manifest-matching hardware baseline and
system Python with NumPy/SciPy/Pillow for the path proposer. Do not run while
another process owns the candidate for review or finish integration.
"""
from pathlib import Path
import subprocess,sys
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
KPY=Path('/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9')
CLI=Path('/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli')
P=Path.home()/'Repositories/ai-working/scratch/stratolink-release-20261012/as7331/candidate'
def run(*args):subprocess.run([str(x) for x in args],cwd=ROOT,check=True)
run(KPY,HERE/'build_candidate.py')
run(KPY,HERE/'dump_geometry.py',P/'stratolink.kicad_pcb',HERE/'unrouted-geometry.json')
run('python3',HERE/'route_candidate.py')
run(KPY,HERE/'finalize_geometry.py')
run(KPY,HERE/'apply_local_bus.py')
run(KPY,HERE.parent/'review/propose_courtyards.py','--project',P,'--r27-y','34.08')
run(KPY,HERE.parent/'review/propose_uv_ground.py','--pcb',P/'stratolink.kicad_pcb')
run(KPY,HERE/'close_right_ground.py')
run(KPY,'-c','import pcbnew,wx,sys; app=wx.App(False); b=pcbnew.LoadBoard(sys.argv[1]); pcbnew.ZONE_FILLER(b).Fill(b.Zones()); pcbnew.SaveBoard(sys.argv[1],b)',P/'stratolink.kicad_pcb')
run(CLI,'sch','erc','--format','json','--output',HERE/'final-erc.json',P/'stratolink.kicad_sch')
run(CLI,'pcb','drc','--refill-zones','--schematic-parity','--format','json','--output',HERE/'pre-finish-drc.json',P/'stratolink.kicad_pcb')
print('Scratch electrical candidate rebuilt. Apply independent green/no-silk finish and final review before manufacture.')
