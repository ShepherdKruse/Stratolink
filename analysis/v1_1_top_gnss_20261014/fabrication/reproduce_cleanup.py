#!/usr/bin/env python3
"""Reproduce the final copper cleanup in an explicit isolated project.

The source project is read-only. The output must not exist. Tool paths can be
supplied for another KiCad installation; this script uses only Python stdlib.
"""
from pathlib import Path
import argparse,hashlib,json,shutil,subprocess,sys

HERE=Path(__file__).resolve().parent
EXPECTED_SOURCE='7e401900a78b7d88c4e688fdbe58039308113fc0308e5125366d0a98c592a502'
EXPECTED_FINAL='88f82c85d2d47b4aea2e7d7d2827c4a92c339788cc0d9c880dd6342ee0440c0a'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-project',type=Path,required=True)
    parser.add_argument('--output-project',type=Path,required=True)
    parser.add_argument('--native-python',default='/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9')
    parser.add_argument('--kicad-cli',default='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli')
    args=parser.parse_args()
    source=args.source_project.resolve()
    output=args.output_project.resolve()
    canonical=(HERE.parents[2]/'hardware/pcb').resolve()
    if output.exists() or output==source or output==canonical or canonical in output.parents or source in output.parents:
        parser.error('Output must be a new isolated project outside the source and canonical hardware directories.')
    source_pcb=source/'stratolink.kicad_pcb'
    if sha(source_pcb)!=EXPECTED_SOURCE:
        parser.error('Source PCB hash does not match the reviewed original-top author candidate.')
    output.mkdir(parents=True)
    for name in ['stratolink.kicad_pcb','stratolink.kicad_pro','stratolink.kicad_sch','stratolink.kicad_dru','fp-lib-table','sym-lib-table']:
        shutil.copy2(source/name,output/name)
    for name in ['lib','3d']:
        if (source/name).exists():
            shutil.copytree(source/name,output/name,symlinks=False)
    commands=[
        [args.native_python,str(HERE/'apply_cleanup.py'),'--pcb',str(output/'stratolink.kicad_pcb'),'--plan',str(HERE/'cleanup-plan.json'),'--ledger',str(output/'cleanup-ledger.json')],
        [args.kicad_cli,'pcb','drc','--refill-zones','--save-board','--schematic-parity','--severity-all','--format','json','--output',str(output/'drc.json'),str(output/'stratolink.kicad_pcb')],
    ]
    for index,command in enumerate(commands):
        with (output/f'step-{index+1}.log').open('w') as log:
            subprocess.run(command,check=True,stdout=log,stderr=subprocess.STDOUT)
    final=sha(output/'stratolink.kicad_pcb')
    drc=json.loads((output/'drc.json').read_text())
    counts={key:len(drc[key])for key in ['violations','unconnected_items','schematic_parity']}
    report=dict(source_sha256=EXPECTED_SOURCE,expected_final_sha256=EXPECTED_FINAL,actual_final_sha256=final,exact_reproduction=final==EXPECTED_FINAL,source_bytes_unchanged=sha(source_pcb)==EXPECTED_SOURCE,drc_counts=counts,commands=commands)
    (output/'reproduction.json').write_text(json.dumps(report,indent=2)+'\n')
    assert report['exact_reproduction'] and report['source_bytes_unchanged'] and not any(counts.values()), report
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    main()
