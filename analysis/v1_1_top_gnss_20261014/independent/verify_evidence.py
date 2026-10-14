#!/usr/bin/env python3
"""Verify portable independent-review evidence and its exact current PCB."""
from pathlib import Path,PurePosixPath
import argparse,hashlib,json
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[3]);p.add_argument('--pcb',type=Path);p.add_argument('--output',type=Path);a=p.parse_args();here=Path(__file__).resolve().parent;m=json.loads((here/'manifest.json').read_text());fail=[]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for group,root in [('files',here),('repository_dependencies',a.repo)]:
 for name,digest in m[group].items():
  rel=PurePosixPath(name);assert not rel.is_absolute()and '..'not in rel.parts
  p=(root/name).resolve();assert p.is_relative_to(root.resolve())
  if not p.is_file()or sha(p)!=digest:fail.append(group+':'+name)
board=a.pcb or a.repo/m['pcb_path']
if not board.is_file()or sha(board)!=m['pcb_sha256']:fail.append('current PCB')
r={'pcb_sha256':m['pcb_sha256'],'manifest_sha256':sha(here/'manifest.json'),'verified_local_files':len(m['files']),'verified_repository_dependencies':len(m['repository_dependencies']),'failures':fail,'passed':not fail}
if a.output:assert not a.output.exists();a.output.write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps(r,indent=2));raise SystemExit(2 if fail else 0)
