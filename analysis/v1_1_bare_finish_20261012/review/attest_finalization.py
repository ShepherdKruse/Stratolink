#!/usr/bin/env python3
"""Independent exact-scope attestation for final blank-line normalization.

Run with KiCad's Python. No physical checks are repeated: every changed file
must have an identical complete parse tree; all remaining files must be exact.
"""
from pathlib import Path
import importlib.util,json,re
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('native_review',HERE/'verify_native.py');v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
EXPECTED={
 'stratolink.kicad_pcb':(21,'c0278f66e3eae9c135da38b97afaa241990706feb0ae730cbd5dc9a1a9ee4603','ea78337c91c73d27b813f09f74dd2d2993e5a82d09800362d82c49a0c4f3ed96'),
 'lib/Stratolink_GNSS_Wire_PTH_D1p0.kicad_mod':(18,'362c70435248e198cec1006944264f4c3a20c5b34dc55fafcde1096616b5baea','3ce5f2f3ca3e850c9f6a108c82058d5ce4b7d4f267c4ef480d9010c1bc913468'),
 'lib/Stratolink_LoRa_Wire_PTH_D1p0.kicad_mod':(18,'6676e1f0e85b33b5cc2bbff20d038db687fed4f4fbd1701b1c78c8975010ab48','9634c73a0eadb59d2ec6e7f6e0a98329c0f0cf281fa7b0f27688cb449698a2d1')}
def main():
 old=json.loads((HERE.parent/'reviewed-candidate.json').read_text());new=json.loads((HERE.parent/'candidate.json').read_text())
 a,b=Path(old['candidate']),Path(new['candidate']);assert a!=b
 assert len(old['files'])==len(new['files'])==91 and old['files'].keys()==new['files'].keys()
 changed=[]
 for name,sha in old['files'].items():
  assert v.digest(a/name)==sha,('Reviewed frozen candidate modified',name)
  assert v.digest(b/name)==new['files'][name],('Final candidate manifest mismatch',name)
  if (a/name).read_bytes()!=(b/name).read_bytes():changed.append(name)
 assert set(changed)==set(EXPECTED)
 normalized={}
 for name,(count,before_sha,after_sha) in EXPECTED.items():
  before,after=[(p/name).read_text() for p in [a,b]]
  assert v.a.parse(before)==v.a.parse(after),('Semantic tree changed',name)
  lines=re.findall(r'(?m)^[ \t]+$',before);assert len(lines)==count,(name,len(lines))
  assert re.sub(r'(?m)^[ \t]+$','',before)==after,('Difference is not solely blank-line whitespace removal',name)
  assert v.digest(a/name)==before_sha and v.digest(b/name)==after_sha
  normalized[name]=dict(before_sha256=before_sha,after_sha256=after_sha,blank_lines_normalized=count,entire_parse_tree_exact=True,only_removed_blank_line_whitespace=True)
 result=dict(status='passed',reviewed_candidate=str(a),final_candidate=str(b),reviewed_pcb_sha256=EXPECTED['stratolink.kicad_pcb'][1],final_pcb_sha256=EXPECTED['stratolink.kicad_pcb'][2],normalized_files=normalized,other_88_cad_library_files_byte_exact=True,all_91_manifest_hashes_verified=True,prior_verification_sha256=v.digest(HERE/'verification.json'),geometry_verification_sha256=v.digest(HERE/'geometry-verification.json'),interpretation='Final bytes differ only by whitespace on 21 blank PCB lines and 18 blank lines in each of the two new antenna footprints. Complete parse trees are exact for all three changed files; the other 88 files are byte-identical. Previous native connectivity, DRC and fabrication evidence therefore applies to this final source without a second broad test run.')
 (HERE/'finalization-attestation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
