#!/usr/bin/env python3
"""Compare fresh native Gerbers; only U7 front-mask aperture macros may change."""
from pathlib import Path
import re,hashlib,json,zipfile
H=Path(__file__).resolve().parent;S=Path.home()/'Repositories/ai-working/scratch/stratolink-u7-mask'
def strip(s):return '\n'.join(l for l in s.splitlines() if 'CreationDate' not in l and not l.startswith('G04 Created by'))
files={};changed=[]
for p in sorted((S/'exports-before').glob('*')):
 if p.suffix=='.gbrjob':continue
 q=S/'exports-after'/p.name;a,b=strip(p.read_text()),strip(q.read_text());same=a==b
 files[p.name]={'before_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'after_sha256':hashlib.sha256(q.read_bytes()).hexdigest(),'same_after_timestamp_removal':same}
 if not same:changed.append(p.name)
assert changed==['stratolink-F_Mask.gts']
a,b=(strip((S/n/'stratolink-F_Mask.gts').read_text()) for n in ['exports-before','exports-after'])
macro=lambda s:{int(m.group(1)):m.group(0) for m in re.finditer(r'%ADD(\d+)RoundRect,[^\n]+',s)}
ma,mb=macro(a),macro(b);ids=[i for i in ma if ma[i]!=mb[i]];assert ids==[18,19]
assert re.sub(r'%ADD(?:18|19)RoundRect,[^\n]+','MASK_APERTURE',a)==re.sub(r'%ADD(?:18|19)RoundRect,[^\n]+','MASK_APERTURE',b)
ref=None;ap=None;flashes=[]
for line in b.splitlines():
 m=re.fullmatch(r'%TO.C,([^*]+)\*%',line)
 if m:ref=m.group(1)
 if line=='%TD*%':ref=None
 m=re.fullmatch(r'D(\d+)\*',line)
 if m:ap=int(m.group(1))
 if 'D03*' in line and ap in ids:flashes.append(dict(ref=ref,aperture=ap,command=line))
assert len(flashes)==12 and all(p['ref']=='U7' for p in flashes),flashes
out=H/'review-gerbers.zip'
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
 for p in sorted((S/'exports-after').glob('*')):z.write(p,p.name)
result=dict(status='pass',unchanged_layers=[n for n,d in files.items() if d['same_after_timestamp_removal']],changed_layer='F.Mask',change='Only two aperture macros used exclusively by the12U7padflashes. Coordinates/othermacros/plotcommands exact.',old_U7_apertures={i:ma[i] for i in ids},new_U7_apertures={i:mb[i] for i in ids},U7_flashes=flashes,files=files,archive_sha256=hashlib.sha256(out.read_bytes()).hexdigest())
(H/'gerber-verification.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'],len(flashes),'U7 flashes; unchanged copper, paste and back mask')
