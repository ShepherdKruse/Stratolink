#!/usr/bin/env python3
"""Create a project-aware CLI-refilled analysis copy without changing source CAD."""
from pathlib import Path
import argparse,hashlib,json,shutil,subprocess
HERE=Path(__file__).resolve().parent
SCRATCH=Path.home()/'Repositories/ai-working/scratch/stratolink-release-20261012/as7331/review'
CLI='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--project',type=Path,required=True);ap.add_argument('--name',choices=['baseline','candidate'],required=True);a=ap.parse_args();out=SCRATCH/('refill-'+a.name);out.mkdir(parents=True,exist_ok=True)
    rels=['stratolink.kicad_pcb','stratolink.kicad_pro','stratolink.kicad_dru','fp-lib-table','sym-lib-table']
    rels += [str(p.relative_to(a.project)) for p in (a.project/'lib').rglob('*') if p.is_file() and p.suffix in ['.kicad_mod','.kicad_sym']]
    hashes={n:sha(a.project/n) for n in rels if (a.project/n).exists()}
    if a.name=='baseline':assert hashes['stratolink.kicad_pcb']=='8e2f83797dd68195aa71b73fc252fe57e53ccd3683ef5f74739dc4d25d6ce8d5'
    for n in hashes:(out/n).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(a.project/n,out/n)
    cmd=[CLI,'pcb','drc','--refill-zones','--save-board','--severity-all','--format','json','--output',str(out/'refill-drc.json'),str(out/'stratolink.kicad_pcb')]
    r=subprocess.run(cmd,text=True,capture_output=True,check=True);(out/'refill.log').write_text(r.stdout+r.stderr)
    for n,v in hashes.items():assert sha(a.project/n)==v,('Source changed during CLI fill',n)
    result=dict(source=str(a.project),source_hashes=hashes,refilled_pcb=str(out/'stratolink.kicad_pcb'),refilled_pcb_sha256=sha(out/'stratolink.kicad_pcb'),command=cmd,note='Refilled saved analysis copy with real project/rules. Input CAD unchanged. DRC report here is fill evidence, not the final schematic-parity release DRC.')
    (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='source_hashes'},indent=2))
if __name__=='__main__':main()
