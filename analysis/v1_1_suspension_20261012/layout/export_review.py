#!/usr/bin/env python3
"""Export the frozen scratch candidate only, with source hash guard."""
from pathlib import Path
import subprocess,hashlib,json,re
HERE=Path(__file__).resolve().parent
OUT=HERE/'fabrication';OUT.mkdir(exist_ok=True)
BOARD=Path.home()/'Repositories/ai-working/scratch/stratolink-suspension-pth/candidate/stratolink.kicad_pcb'
before=hashlib.sha256(BOARD.read_bytes()).hexdigest()
assert before=='82926d9dfc728dca41c9d0970c69a5144fb9079380a298337381c199698f80f4'
CLI='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
commands=[
 [CLI,'pcb','export','drill','--output',str(OUT)+'/', '--format','excellon','--excellon-units','mm','--excellon-separate-th','--generate-report','--report-path',str(OUT/'drill-report.txt'),str(BOARD)],
 [CLI,'pcb','export','gerbers','--output',str(OUT)+'/', '--layers','F.Cu,B.Cu,F.Mask,B.Mask,F.Paste,B.Paste,Edge.Cuts',str(BOARD)]]
for i,cmd in enumerate(commands):
 run=subprocess.run(cmd,check=True,text=True,capture_output=True)
 (OUT/f'export-{i}.log').write_text(run.stdout+run.stderr)
pth=(OUT/'stratolink-PTH.drl').read_text();npth=(OUT/'stratolink-NPTH.drl').read_text()
tools={m.group(1):float(m.group(2)) for m in re.finditer(r'^T(\d+)C([\d.]+)$',pth,re.M)}
current=None;hits=[]
for line in pth.splitlines():
 if re.fullmatch(r'T\d+',line):current=line[1:]
 m=re.fullmatch(r'X([\d.-]+)Y([\d.-]+)',line)
 if m:hits.append(dict(tool=current,diameter_mm=tools[current],x_mm=float(m.group(1)),y_mm=-float(m.group(2))))
new=[h for h in hits if h['diameter_mm']==2]
assert [(h['x_mm'],h['y_mm']) for h in new]==[(55.665,31.745),(74.327,31.745)]
assert 'Plated' in pth and 'NonPlated' in npth
npth_hits=[(float(m.group(1)),-float(m.group(2))) for m in re.finditer(r'^X([\d.-]+)Y([\d.-]+)$',npth,re.M)]
assert sorted(npth_hits)==sorted([(57.764,83.688),(62.844,84.704),(62.844,82.672)]), 'Existing bottom NPTH holes changed'
for layer in ['F_Paste','B_Paste']:
 assert not re.search(r'%TO\.C,H[12]\*%',(OUT/f'stratolink-{layer}.gtp' if layer=='F_Paste' else OUT/f'stratolink-{layer}.gbp').read_text())
after=hashlib.sha256(BOARD.read_bytes()).hexdigest();assert before==after
files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file() and p.suffix not in ['.log','.json']}
result=dict(candidate_sha256=before,plated_2mm_hits=new,unchanged_bottom_npth_drill_hits=npth_hits,manual_contacts_have_no_paste=True,exports_sha256=files,note='Source and exports checked; separate independent fabrication review also requested. No order release.')
(OUT/'export-evidence.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
