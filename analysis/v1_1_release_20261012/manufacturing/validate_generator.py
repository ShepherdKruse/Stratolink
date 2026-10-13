#!/usr/bin/env python3
"""Exercise the release generator against three independent manufacturing mistakes."""
from pathlib import Path
import argparse,hashlib,json,shutil,subprocess,sys
import pcbnew,wx
HERE=Path(__file__).resolve().parent

def mutate(pcb,case):
    app=wx.App(False);b=pcbnew.LoadBoard(str(pcb));fps={f.GetReference():f for f in b.GetFootprints()}
    if case=='missing-supplier':fps['R8'].GetField('Supplier Part').SetText('')
    elif case=='duplicate-ref':fps['R18'].SetReference('R10')
    elif case=='inconsistent-population':fps['R8'].SetExcludedFromBOM(True)
    else:
        for item in list(b.GetDrawings()):
            if item.GetLayer() in {pcbnew.F_Mask,pcbnew.B_Mask}:b.Remove(item)
    pcbnew.SaveBoard(str(pcb),b)

def main():
    p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--scratch',type=Path,required=True);args=p.parse_args()
    args.scratch.mkdir(parents=True,exist_ok=False);app=wx.App(False);result=[]
    source=args.candidate/'stratolink.kicad_pcb';sourcehash=hashlib.sha256(source.read_bytes()).hexdigest()
    for case,expected in [('missing-supplier','PCB/SCH missing or differing Supplier Part for R8'),('duplicate-ref','Candidate PCB duplicate R10'),('missing-mask-opening','No full-face opening rectangle'),('inconsistent-population','Inconsistent BOM/placement exclusions for R8')]:
        folder=args.scratch/case;shutil.copytree(args.candidate,folder);pcb=folder/'stratolink.kicad_pcb'
        subprocess.run([sys.executable,str(__file__),'--mutate',str(pcb),case],check=True,capture_output=True)
        command=[sys.executable,str(HERE/'generate.py'),'--candidate',str(folder),'--output',str(args.scratch/(case+'-output'))]
        run=subprocess.run(command,capture_output=True,text=True);(args.scratch/(case+'.log')).write_text(run.stdout+run.stderr)
        assert run.returncode!=0 and expected in run.stderr,(case,run.returncode,run.stderr)
        assert not (args.scratch/(case+'-output/manifest.json')).exists()
        result.append(dict(case=case,expected_failure=expected,rejected=True,no_success_manifest=True))
    assert hashlib.sha256(source.read_bytes()).hexdigest()==sourcehash
    report=dict(source=str(args.candidate),source_pcb_sha256=sourcehash,source_unchanged=True,cases=result)
    (HERE/'negative-validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--mutate':mutate(Path(sys.argv[2]),sys.argv[3])
    else:main()
