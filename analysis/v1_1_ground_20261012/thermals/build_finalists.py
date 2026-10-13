#!/usr/bin/env python3
"""Bounded scratch-only comparison of explicit trace-fed and thermal options."""
from pathlib import Path
import json,sys,subprocess,concurrent.futures
H=Path(__file__).resolve().parent;ROOT=H.parents[2];BASE='c3d70a429a95591607341d57bf16ee153972da71';S=Path.home()/'Repositories/ai-working/scratch/stratolink-zones-20261012/thermal';CLI='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
sys.path.insert(0,str(ROOT/'analysis/v1_1_solar_attachments_20261012/layout'));import cad_helpers as a
source=(H/'build_trials.py').read_text();exec(source[source.index('def spans'):source.index("if '--mixed-only'")])
thermal=lambda angle:f'(thermal_gap 0.25) (thermal_bridge_width 0.25) (thermal_bridge_angle {angle})'
trials=[
 dict(name='trace_only_5_7_8',pads={p:'(zone_connect 0)' for p in ['5','7','8']}),
 dict(name='trace_only_3_5_7_8',pads={p:'(zone_connect 0)' for p in ['3','5','7','8']}),
 dict(name='trace_only_5_8',pads={'5':'(zone_connect 0)','8':'(zone_connect 0)'}),
 dict(name='trace_only_ground_cluster',pads={p:'(zone_connect 0)' for p in ['3','5','6','7','8']}),
 dict(name='cluster_5_7_8_g250_w250_7a90',pads={'5':thermal(45),'7':thermal(90),'8':thermal(90)}),
 dict(name='cluster_5_7_8_g250_w250_7a45',pads={'5':thermal(45),'7':thermal(45),'8':thermal(90)}),
]
if '--minimal-only' in sys.argv:trials=trials[:2]
for trial in trials:
 out=S/trial['name'];out.mkdir(exist_ok=True)
 for name in ['stratolink.kicad_pcb','stratolink.kicad_sch','stratolink.kicad_pro','fp-lib-table','sym-lib-table']:(out/name).write_bytes(subprocess.check_output(['git','show',BASE+':hardware/pcb/'+name],cwd=ROOT))
 for name in ['lib','3d']:
  if not (out/name).exists():(out/name).symlink_to(ROOT/'hardware/pcb'/name)
 text=(out/'stratolink.kicad_pcb').read_text();fps=[]
 for st,en,depth in spans(text):
  if depth!=1:continue
  fptext=text[st:en];f=a.parse(fptext)
  if f[0]!='footprint' or a.prop(f,'Reference') not in ['U7','J20']:continue
  ref=a.prop(f,'Reference');pads=[]
  for ps,pe,pd in spans(fptext):
   if pd!=1:continue
   p=a.parse(fptext[ps:pe])
   if p[0]!='pad':continue
   if ref=='U7' and p[1] in trial['pads']:fields=trial['pads'][p[1]]
   elif ref=='J20' and p[1]=='5':fields='(zone_connect 2)'
   else:continue
   pads.append((ps,pe,fptext[ps:pe].rstrip()[:-1]+' '+fields+')'))
  fps.append((st,en,rewrite(fptext,pads)))
 (out/'stratolink.kicad_pcb').write_text(rewrite(text,fps));trial['directory']=str(out)
def check(t):
 p=Path(t['directory']);r=subprocess.run([CLI,'pcb','drc','--refill-zones','--save-board','--schematic-parity','--format','json','--output',str(p/'drc.json'),str(p/'stratolink.kicad_pcb')],capture_output=True,text=True)
 (p/'drc.log').write_text(r.stdout+r.stderr);assert r.returncode==0,(t,r.stdout,r.stderr)
 dr=json.loads((p/'drc.json').read_text());return t|dict(violations=len(dr['violations']),opens=len(dr['unconnected_items']),parity=len(dr['schematic_parity']),thermals=[v for v in dr['violations'] if v['type']=='starved_thermal'])
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(check,trials))
(H/('minimal-results.json' if '--minimal-only' in sys.argv else 'finalist-results.json')).write_text(json.dumps(dict(baseline=BASE,trials=results),indent=2)+'\n')
for r in results:print(r['name'],r['violations'],r['opens'],[(v['items'][1]['description'],v['description']) for v in r['thermals']])
