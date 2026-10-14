#!/usr/bin/env python3
"""Verify native project/library bytes against a reviewed comparison manifest.
Allows reproduction without retaining a second full library/model directory.
"""
from pathlib import Path,PurePosixPath
import argparse,hashlib,json
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--project',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--output',type=Path);p.add_argument('--project-file',type=Path,help='Explicit reviewed strict project override; all other files remain from --project')
a=p.parse_args();m=json.loads(a.manifest.read_text());assert m['all_identical']is True
root=a.project.resolve();fail=[];seen=set()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for row in m['files']:
 name=row['path'];q=PurePosixPath(name)
 assert not q.is_absolute()and '..'not in q.parts and name not in seen,name;seen.add(name)
 target=(root/name).resolve();assert target.is_relative_to(root),name
 if name=='stratolink.kicad_pro'and a.project_file:target=a.project_file.resolve()
 assert row['identical']is True and row['before_sha256']==row['after_sha256'],row
 if not target.is_file()or sha(target)!=row['after_sha256']:fail.append(name)
board=root/'stratolink.kicad_pcb'
if not board.is_file()or sha(board)!=m['pcb_sha256']:fail.append('stratolink.kicad_pcb')
r={'pcb_sha256':m['pcb_sha256'],'comparison_manifest_sha256':sha(a.manifest),'verified_project_and_library_files':len(seen),'failures':fail,'passed':not fail,'explicit_project_override':str(a.project_file)if a.project_file else None,'project_at_board_directory_sha256':sha(root/'stratolink.kicad_pro')}
if a.output:
 assert not a.output.exists(),a.output;a.output.write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps(r,indent=2))
if fail:raise SystemExit(2)
