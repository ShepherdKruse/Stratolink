from pathlib import Path
import shutil,json,subprocess
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];OUT=Path.home()/'Repositories/ai-working/scratch/stratolink-release-20261012/identities';CLI='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
for label,src in [('baseline',OUT/'metadata-candidate'),('candidate',OUT/'u7-candidate')]:
 for gap in [.1,.15]:
  dst=OUT/(label+'-u7-screen-'+str(gap));dst.mkdir(exist_ok=True)
  for n in ['stratolink.kicad_pcb','stratolink.kicad_sch','stratolink.kicad_pro','fp-lib-table','sym-lib-table']:shutil.copyfile(src/n,dst/n)
  # Read-only libraries under copied candidate, explicit path to preserve exact fixture.
  s=(dst/'fp-lib-table').read_text().replace('${KIPRJMOD}',str(src));(dst/'fp-lib-table').write_text(s)
  s=(dst/'sym-lib-table').read_text().replace('${KIPRJMOD}',str(src));(dst/'sym-lib-table').write_text(s)
  p=dst/'stratolink.kicad_pro';j=json.loads(p.read_text());d=j['board']['design_settings'];d['rules']['min_clearance']=gap;d['rules']['min_copper_edge_clearance']=.2;d['rule_severities']['clearance']='error';d['rule_severities']['copper_edge_clearance']='error';
  for c in j['net_settings']['classes']:c['clearance']=gap
  p.write_text(json.dumps(j))
  dest=HERE/(label+'-u7-screen-'+str(gap)+'.json');r=subprocess.run([CLI,'pcb','drc','--refill-zones','--schematic-parity','--format','json','--output',str(dest),str(dst/'stratolink.kicad_pcb')],capture_output=True,text=True);(dst/'drc.log').write_text(r.stdout+r.stderr);assert r.returncode==0
  print(label,gap,len(json.loads(dest.read_text())['violations']),flush=True)
