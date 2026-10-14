#!/usr/bin/env python3
"""Repeat the accepted top-GNSS independent checks into a new scratch directory."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[3]);p.add_argument('--pcb',type=Path);p.add_argument('--output',type=Path,required=True)
p.add_argument('--native-python',type=Path,default=Path('/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9'))
a=p.parse_args();here=Path(__file__).resolve().parent;pcb=a.pcb or a.repo/'hardware/pcb/stratolink.kicad_pcb';assert not a.output.exists();a.output.mkdir(parents=True)
expected=json.loads((here/'reports/acceptance.json').read_text());assert hashlib.sha256(pcb.read_bytes()).hexdigest()==expected['pcb_sha256']
assert hashlib.sha256((pcb.parent/'stratolink.kicad_pro').read_bytes()).hexdigest()in[expected['canonical_project_sha256'],expected['strict_project_sha256']]
commands=[]
def run(argv,name,allowed=(0,)):
 argv=[str(x)for x in argv];commands.append(argv);r=subprocess.run(argv,capture_output=True,text=True);(a.output/(name+'.log')).write_text(r.stdout+r.stderr);assert r.returncode in allowed,(name,r.returncode,r.stderr)
common=[sys.executable]
run([*common,here/'audit_candidate.py','--repo',a.repo,'--before',here/'inputs/before-8df85.kicad_pcb','--after',pcb,'--before-sha256',expected['before_pcb_sha256'],'--after-sha256',expected['pcb_sha256'],'--expected-poses',here/'declarations/poses.json','--expected-edits',here/'declarations/edits.json','--output',a.output/'audit','--native-python',a.native_python,*[v for net in ['GND','Net-(AE2-A)','+SOLAR','Net-(U1-LBOOST)','/VBAT','/SC_BAL_OUT']for v in ['--allowed-route-net',net]]],'audit',allowed=(2,))
run([a.native_python,here/'extract_zone_settings.py','--repo',a.repo,'--pcb',pcb,'--output',a.output/'zones.json'],'zones')
run([*common,here/'connected_guard_report.py','--repo',a.repo,'--geometry',a.output/'audit/after-reference-geometry.json','--output',a.output/'connected-guard.json'],'connected-guard')
run([a.native_python,here/'check_artwork_moves.py','--repo',a.repo,'--before',here/'inputs/before-8df85.kicad_pcb','--after',pcb,'--plan',here/'declarations/artwork.json','--output',a.output/'artwork.json'],'artwork')
run([*common,here/'verify_project_files_manifest.py','--project',pcb.parent,'--manifest',here/'reports/project-library.json','--project-file',here/'inputs/strict-project.kicad_pro','--output',a.output/'project-library.json'],'project-library')
run([*common,here/'check_final_geometry.py','--geometry',a.output/'audit/candidate-geometry.json','--reference-geometry',a.output/'audit/after-reference-geometry.json','--zones',a.output/'zones.json','--screen',a.output/'audit/etch-screen.json','--reference',a.output/'audit/reference.json','--output',a.output/'geometry-disposition.json'],'disposition')
run([*common,here/'compare_cleanup_copper.py','--before',here/'inputs/pre-cleanup-geometry.json','--after',a.output/'audit/candidate-geometry.json','--output',a.output/'cleanup-copper-delta.json'],'delta')
s=json.loads((a.output/'audit/summary.json').read_text());d=json.loads((a.output/'geometry-disposition.json').read_text());assert all(v for k,v in s['checks'].items()if k!='no_screened_etch_candidates');assert s['checks']['no_screened_etch_candidates']is False and d['all_checks_pass']is True
assert d['residual_feature_count']==expected['raw_screen_flag_count']and abs(d['maximum_residual_inscribed_diameter_nm']-expected['maximum_residual_inscribed_diameter_nm'])<.01
report={'pcb_sha256':expected['pcb_sha256'],'accepted_review_reproduced':True,'raw_numerical_findings_preserved':True,'commands':commands};(a.output/'reproduction.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items()if k!='commands'},indent=2))
