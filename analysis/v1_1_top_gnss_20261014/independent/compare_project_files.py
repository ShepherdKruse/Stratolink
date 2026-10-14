#!/usr/bin/env python3
"""Read-only exact project and active-library comparison for a routing-only edit."""
from pathlib import Path
import argparse,hashlib,json
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--before',type=Path,required=True,help='Directory containing before stratolink.kicad_pcb')
p.add_argument('--after',type=Path,required=True,help='Directory containing after stratolink.kicad_pcb')
p.add_argument('--output',type=Path,required=True)
a=p.parse_args();assert not a.output.exists(),a.output
main={'stratolink.kicad_sch','stratolink.kicad_pro','stratolink.kicad_dru','fp-lib-table','sym-lib-table'}
names=set(main)
for root in [a.before,a.after]:
 names.update(p.relative_to(root).as_posix()for p in (root/'lib').rglob('*')if p.is_file())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()if p.is_file()else None
rows=[]
for name in sorted(names):
 old,new=a.before/name,a.after/name;b,c=sha(old),sha(new)
 rows.append({'path':name,'before_sha256':b,'after_sha256':c,'identical':b is not None and b==c})
r={'before_pcb_sha256':sha(a.before/'stratolink.kicad_pcb'),'pcb_sha256':sha(a.after/'stratolink.kicad_pcb'),'compared_file_count':len(rows),'all_identical':all(r['identical']for r in rows),'files':rows,'checker_sha256':sha(Path(__file__))}
a.output.write_text(json.dumps(r,indent=2)+'\n');print(r['compared_file_count'],r['all_identical'])
if not r['all_identical']:raise SystemExit(2)
