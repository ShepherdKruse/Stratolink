#!/usr/bin/env python3
"""Initial microphone ECO against a frozen Git baseline. Not a general editor.

Run once, with KiCad editors closed. Refuses to overwrite later CAD changes.
"""
from pathlib import Path
import hashlib, json, re, subprocess, uuid
import xml.etree.ElementTree as ET

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
BASE='38de8d750c476258ba217c76274216863cf0b29c'
PCB=ROOT/'hardware/pcb/stratolink.kicad_pcb'
SCH=ROOT/'hardware/pcb/stratolink.kicad_sch'

def spans(text):
    stack=[]; result=[]; quoted=False; escaped=False
    for i,c in enumerate(text):
        if quoted:
            if escaped:escaped=False
            elif c=='\\':escaped=True
            elif c=='"':quoted=False
        elif c=='"':quoted=True
        elif c=='(':stack.append(i)
        elif c==')':result.append((stack.pop(),i+1,len(stack)))
    assert not stack and not quoted
    return result

def parse(text):
    stack=[];root=None
    for t in re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+',text):
        if t=='(':
            n=[]
            if stack:stack[-1].append(n)
            else:root=n
            stack.append(n)
        elif t==')':stack.pop()
        else:stack[-1].append(json.loads(t) if t.startswith('"') else t)
    return root

def children(n,k):return [x for x in n if isinstance(x,list) and x and x[0]==k]
def field(n,k,default=None):
    v=children(n,k);return v[0][1] if v else default
def prop(n,k):return next((p[2] for p in children(n,'property') if p[1]==k),None)
def top(text):return [(a,b,parse(text[a:b])) for a,b,d in spans(text) if d==1]
def remove(text,where):
    for a,b in sorted(where,reverse=True):text=text[:a]+text[b:]
    return text
def sha(b):return hashlib.sha256(b).hexdigest()

source={}
for p in [PCB,SCH]:
    rel=str(p.relative_to(ROOT));old=subprocess.check_output(['git','show',BASE+':'+rel],cwd=ROOT)
    assert p.read_bytes()==old,('Working CAD differs from frozen baseline',rel)
    source[rel]=sha(old)

s=SCH.read_text();drop=[];removed_schematic=[]
mic_symbols={'MK1','C13','R20','#PWR033','#PWR034'}
for a,b,n in top(s):
    delete=False;k=n[0]
    if k=='symbol':delete=prop(n,'Reference') in mic_symbols
    elif k=='global_label':delete=n[1] in {'CLK','PDM'}
    elif k=='wire':
        xy=children(children(n,'pts')[0],'xy')
        inside=all(13.97<float(p[1])<76.835 and 88.265<float(p[2])<121.92 for p in xy)
        delete=inside or field(n,'uuid') in {'312cb211-d69c-4969-9310-871fab8eb6a2','5691af9a-9c2a-4cae-9f8a-2c43cb86057c'}
    elif k in {'junction','rectangle','text'}:
        delete=field(n,'uuid') in {'96ace5a1-f35e-4e7d-b7a0-b673b1ce359a','ba27e3dc-ece0-4661-bd25-c7becfaa61b6','6fe1f475-e7f6-482f-864d-f77e0ca263ef','857cefa3-b68e-4ef2-8e65-a7a70949e8e9'}
    if delete:
        drop.append((a,b));removed_schematic.append({'kind':k,'reference':prop(n,'Reference'),'uuid':field(n,'uuid')})
assert len(removed_schematic)==26,len(removed_schematic)
s=remove(s,drop)
# The T3902 cached definition is no longer instantiated.
lib=next((a,b) for a,b,d in spans(s) if s[a:b].startswith('(symbol "T3902:T3902"'))
s=remove(s,[lib])
nc=[]
for x,y in [(105.41,52.07),(105.41,54.61)]:
    uid=str(uuid.uuid4());nc.append({'at':[x,y],'uuid':uid})
    s=s.rstrip()[:-1]+f'\n\t(no_connect\n\t\t(at {x} {y})\n\t\t(uuid "{uid}")\n\t)\n)\n'
s=re.sub(r'(?m)^[\t ]+\n','',s)
SCH.write_text(s)

# Derive NC net spelling/types from KiCad, rather than inventing pad metadata.
with (HERE/'netlist-export.log').open('w') as log:
    subprocess.run(['kicad-cli','sch','export','netlist','--format','kicadxml','--output',str(HERE/'netlist.xml'),str(SCH)],stdout=log,stderr=log,check=True)
netlist=ET.parse(HERE/'netlist.xml');nc_pads={}
for net in netlist.findall('.//nets/net'):
    for n in net.findall('node'):
        if n.get('ref')=='U2' and n.get('pin') in {'31','32'}:
            # XML exports human-readable '/', while PCB parity uses the
            # escaped pin-name slash in automatically generated NC net names.
            nc_pads[n.get('pin')]={'net':net.get('name').replace('/', '{slash}'),'pintype':n.get('pintype')}
assert len(nc_pads)==2 and all('no_connect' in p['pintype'] for p in nc_pads.values()),nc_pads

b=PCB.read_text();drop=[];removed_copper=[]
ground_prefixes={'29a1de5e','330720cf','499bc48f','96ca59cc','9993a8c1','b507c960','d7490907','d8592b89','f21803a3','c46247ae','eacfa1bb','30dc1101'}
for a,z,n in top(b):
    k=n[0];uid=field(n,'uuid','')
    delete=(k=='footprint' and prop(n,'Reference') in {'MK1','C13','R20'})
    if k in {'segment','via'}:
        delete=field(n,'net') in {'CLK','PDM','Net-(MK1-CLK)'} or uid[:8] in ground_prefixes
        if delete:removed_copper.append({'kind':k,'uuid':uid,'net':field(n,'net')})
    if delete:drop.append((a,z))
assert len(removed_copper)==30,len(removed_copper)
b=remove(b,drop)
a,z,n=next((a,z,n) for a,z,n in top(b) if n[0]=='footprint' and prop(n,'Reference')=='U2')
u2=b[a:z]
for x,y,d in sorted(spans(u2),reverse=True):
    if d!=1:continue
    part=u2[x:y];m=re.match(r'\(pad "(31|32)"',part)
    if not m:continue
    meta=nc_pads[m[1]]
    part=re.sub(r'\(net "[^"]*"\)',f'(net "{meta["net"]}")',part)
    part=re.sub(r'\(pintype "[^"]*"\)',f'(pintype "{meta["pintype"]}")',part)
    u2=u2[:x]+part+u2[y:]
b=b[:a]+u2+b[z:]
# C13's old power pad bridged these existing track ends. Preserve the shared
# 3.3 V feed to FB1/GNSS when removing the capacitor, with explicit copper.
bridge_uuid=str(uuid.uuid4())
bridge=f'(segment (start 58.1705 53.569) (end 58.3055 53.434) (width 0.25) (layer "F.Cu") (net "+3.3V") (uuid "{bridge_uuid}"))'
b=b.rstrip()[:-1]+'\n\t'+bridge+'\n)\n'
# Removing CLK/PDM changes the adjacent ground pours. Add explicit ground
# connections without changing footprints or relaxing thermal/clearance rules.
ground_connections=[]
for a,z in [([57.549999,71.650001],[59.15,71.650001]),
            ([55.692,65.683998],[55.692,64.95]),
            ([55.692,64.95],[55.891,64.95]),
            ([55.891,64.95],[56.624998,65.683998])]:
    uid=str(uuid.uuid4())
    segment=f'(segment (start {a[0]} {a[1]}) (end {z[0]} {z[1]}) (width 0.25) (layer "F.Cu") (net "GND") (uuid "{uid}"))'
    b=b.rstrip()[:-1]+'\n\t'+segment+'\n)\n'
    ground_connections.append({'uuid':uid,'start':a,'end':z,'width_mm':.25})
PCB.write_text(b)
manifest={'baseline_git_commit':BASE,'baseline_sha256':source,'removed_references':['MK1','C13','R20'],
          'removed_schematic':removed_schematic,'new_no_connects':nc,'u2_nc_pads':nc_pads,
          'removed_copper':removed_copper,'shared_supply_bridge':{'uuid':bridge_uuid,'net':'+3.3V','start':[58.1705,53.569],'end':[58.3055,53.434],'width_mm':.25},
          'ground_fill_connections':ground_connections,
          'note':'Native zone refill and independent connectivity/fabrication verification must follow.'}
(HERE/'changes.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'removed_parts':manifest['removed_references'],'removed_copper_objects':len(removed_copper),'nc_pads':nc_pads},indent=2))
