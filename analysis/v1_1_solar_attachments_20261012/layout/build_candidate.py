#!/usr/bin/env python3
"""Disposable solar-mount routing trial, never writes canonical hardware."""
from pathlib import Path
import re,json,uuid,shutil,subprocess,sys,math
from shapely.geometry import LineString,box
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
OUT=Path.home()/'Repositories/ai-working/scratch/stratolink-solar-anchor/candidate';OUT.mkdir(parents=True,exist_ok=True);(OUT/'lib').mkdir(exist_ok=True)
import cad_helpers as a
BASE='1aed52ff7af3d27aef6ff4b0ceba710c57dc6865'
def uid():return str(uuid.uuid4())
def spans(t):
 stack=[];q=False;esc=False;out=[]
 for i,c in enumerate(t):
  if q:
   if esc:esc=False
   elif c=='\\':esc=True
   elif c=='"':q=False
  elif c=='"':q=True
  elif c=='(':stack.append(i)
  elif c==')':out.append((stack.pop(),i+1,len(stack)))
 return out

def tops(t):return [(s,e,a.parse(t[s:e])) for s,e,d in spans(t) if d==1]
def rewrite(t,replacements):
 for s,e,v in sorted(replacements,reverse=True):t=t[:s]+v+t[e:]
 return t
for name in ['stratolink.kicad_pro','stratolink.kicad_pcb','stratolink.kicad_sch','fp-lib-table','sym-lib-table']:
 p=ROOT/'hardware/pcb'/name;data=subprocess.check_output(['git','show',BASE+':hardware/pcb/'+name],cwd=ROOT);(OUT/name).write_bytes(data)
for p in (ROOT/'hardware/pcb/lib').iterdir():
 if p.name in {'Solar_Notch_Left_1p0x1p5.kicad_mod','Solar_Notch_Right_1p0x1p5.kicad_mod'}:continue
 dest=OUT/'lib'/p.name
 if not dest.exists():dest.symlink_to(p)
b=(OUT/'stratolink.kicad_pcb').read_text();s=(OUT/'stratolink.kicad_sch').read_text();changes=[];drop=set();add=[]
def track(net,layer,pts,width=.25):
 for p,q in zip(pts,pts[1:]):
  if math.dist(p,q)<1e-6:continue
  add.append(f'(segment (start {p[0]} {p[1]}) (end {q[0]} {q[1]}) (width {width}) (layer "{layer}") (net "{net}") (uuid "{uid()}"))')
def via(net,x,y,size=.6,drill=.3):add.append(f'(via (at {x} {y}) (size {size}) (drill {drill}) (layers "F.Cu" "B.Cu") (free yes) (net "{net}") (uuid "{uid()}"))')
def replace(prefixes,net,layer,pts,width=.25):
 drop.update(prefixes.split());track(net,layer,pts,width)

# Front-side notch bypasses, keeping other component placements fixed.
replace('7ceeeec4 8bea6091','VSTOR','F.Cu',[(55.1,51.819),(55.94,52.659),(55.94,56.375),(53.660009,56.375),(53.660009,59.447009)])
replace('54ca047a','PB5','F.Cu',[(75.452,39.709),(75.452,52.33),(73.675,52.33),(73.675,56.775),(75.452,56.775),(75.452,60.494)])
replace('8eb1da3c','VSTOR','F.Cu',[(75.909911,37.588911),(75.909911,52.745),(74.075,52.745),(74.075,56.375),(75.909911,56.375),(75.909911,60.794089)])
replace('4db9a78b abb4a3d6','SDA','F.Cu',[(71.783,54.111),(73.225,55.553),(73.225,61.312),(73.503,61.59)])
replace('4ff0010b cf4fd11f','SDA','F.Cu',[(72.223,58.183),(73.225,58.183)])
# Move the RX layer-change via out of the new ground land.
for st,en,n in tops(b):
 if n[0]=='via' and a.scalar(n,'net')=='RX' and math.dist(a.floats(n,'at'),[74.732,53.024])<.001:drop.add(a.scalar(n,'uuid')[:8])
replace('40844e50 af13b005','RX','F.Cu',[(74.088001,51.71),(74.69,51.71),(74.85,51.55)])
via('RX',74.85,51.55)
replace('3960c325 55413a71 b188a8b1','RX','B.Cu',[(74.85,51.55),(74.1,52.3),(74.1,56.375),(75.827,56.375),(75.827,61.068)])
replace('0f4aa76f 1172538b 31646d6f','TX','B.Cu',[(74.107,49.94),(74.107,51.2),(73.65,51.2),(73.65,56.825),(75.377,56.825),(75.377,60.881604)])
replace('6607f49d','+SOLAR','B.Cu',[(54.148,41.448875),(54.148,52.45),(55.95,52.45),(55.95,56.5),(54.148,56.5),(54.148,57.399)])
replace('f85bb5dc 1524dca1 b24b1af3 4a06860d 75e5ad1a afc7e9e0 ba022d3d dd87340d ec0c022f','+SOLAR','B.Cu',[(73.53,43.771),(73.53,50.7),(73.2,50.7),(73.2,56.0),(72.8,56.4),(72.8,56.64)])
track('+SOLAR','B.Cu',[(68.667,56.64),(72.8,56.64)],.5)
# Retain old left supply layer transition after old plated header pad is gone.
via('+SOLAR',54.781,58.032)
# Long low-current solar wires now terminate near the lower board corners.
track('+SOLAR','B.Cu',[(54.781,58.032),(53.65,59.163),(53.65,64.0),(54.0,64.35)])
via('+SOLAR',54.0,64.35)
track('+SOLAR','F.Cu',[(54.0,64.35),(53.65,64.7),(53.65,78.15),(54.0,78.5)])
via('+SOLAR',54.0,78.5)
track('+SOLAR','B.Cu',[(54.0,78.5),(53.65,78.85),(53.65,83.85),(54.8,85),(55.6,85.8),(74.4,85.8),(75.2,85)])
# Replace redundant ground corners with fresh pour connections.
drop.update('0ebfb82b 3415cb98 6e952998 b07ca176 0ffc55fd 13269fc8 10676ba6'.split())
via('GND',72.5,53.45)
# Move a ground stitching via clear of the new left solar feed.
drop.add('f83d33fd');via('GND',54.3,61.35)
track('GND','B.Cu',[(54.125,61.257),(54.3,61.35)])

# Mirrored custom footprints; local origins at notches for intelligible review.
newfps={};fplib={}
for ref,side,x,powerx in [('J2','Left',53.3165,54.8),('J1','Right',76.6755,75.2)]:
 sign=1 if side=='Left' else -1;name='Solar_Notch_'+side+'_1p0x1p5';y=54.5;inner=x+sign*1.5
 cut=LineString([(x-sign,y),(inner-sign*.5,y)]).buffer(.5,resolution=16)
 envelope=box(min(x+sign*.2,inner+sign*.8),53.1,max(x+sign*.2,inner+sign*.8),55.9)
 land=envelope.difference(cut.buffer(.22,resolution=16))
 coords=[(round(px-x,6),round(py-y,6)) for px,py in land.exterior.coords[:-1]]
 primitives=' '.join(f'(xy {px} {py})' for px,py in coords)
 # Local custom-pad anchor belongs to copper above notch, not in the cut.
 anchor=(sign*.85,-1.05)
 shifted=' '.join(f'(xy {round(px-anchor[0],6)} {round(py-anchor[1],6)})' for px,py in coords)
 old=next(n for _,_,n in tops(b) if n[0]=='footprint' and a.prop(n,'Reference')==ref)
 props=[]
 for n in old:
  if isinstance(n,list) and n[0] in ['path','sheetname','sheetfile']:
   props.append('('+n[0]+' '+json.dumps(n[1])+')')
 fpuid=a.scalar(old,'uuid');path=a.scalar(old,'path')
 def make(fpname,reference):
  lines=[f'(footprint "{fpname}" (version 20260206) (generator "pcbnew") (layer "F.Cu") (uuid "{fpuid}") (at {x} {y})',f'(descr "Manual solar panel ground notch lands, separate lower positive wire pad; unplated edge notch in board outline")',f'(property "Reference" "{reference}" (at 0 -2.2) (layer "F.SilkS") (hide yes) (effects (font (size .8 .8) (thickness .12))))',f'(property "Value" "Solar panel direct solder" (at 0 2.2) (layer "F.Fab") (hide yes) (effects (font (size .8 .8) (thickness .12))))','(attr through_hole exclude_from_pos_files exclude_from_bom)',*props]
  for layer in ['F','B']:
   lines.append(f'(pad "2" smd custom (at {anchor[0]} {anchor[1]}) (size .1 .1) (layers "{layer}.Cu" "{layer}.Mask") (net "GND") (pintype "passive") (zone_connect 2) (uuid "{uid()}") (options (clearance outline) (anchor circle)) (primitives (gr_poly (pts {shifted}) (width 0) (fill yes))))')
  lines.append(f'(pad "1" thru_hole circle (at {powerx-x} {85-y}) (size 1.4 1.4) (drill .7) (layers "*.Cu" "*.Mask") (net "+SOLAR") (pintype "passive") (uuid "{uid()}"))')
  # Two local courtyard islands, never a rectangle enclosing other components.
  for layer in ['F','B']:
   for bb in [(min(.2*sign,2.3*sign)-.25,-1.65,max(.2*sign,2.3*sign)+.25,1.65),(powerx-x-.95,29.55,powerx-x+.95,31.45)]:
    lines.append(f'(fp_rect (start {bb[0]} {bb[1]}) (end {bb[2]} {bb[3]}) (stroke (width .05) (type solid)) (fill none) (layer "{layer}.CrtYd") (uuid "{uid()}"))')
  lines.append(')');return '\n'.join(lines)
 fp=make('lib:'+name,ref);newfps[ref]=fp
 library=make(name,'REF**');library=re.sub(r'\s*\(net "[^"]*"\)','',library);library=re.sub(r'\s*\(path "[^"]*"\)','',library);library=re.sub(r'\s*\(sheet(?:name|file) "[^"]*"\)','',library);library=re.sub(r'\(at '+str(x)+r' '+str(y)+r'\)','(at 0 0)',library,count=1)
 target=OUT/'lib'/(name+'.kicad_mod')
 if target.is_symlink():target.unlink()  # Never follow a former read-only library link when writing our generated footprint.
 target.write_text(library+'\n');fplib[ref]='lib:'+name
 for vy in [53.45,55.55]:via('GND',x+sign*.85,vy)
 # Edge outline: notch has two straight banks and rounded inner tip.
 def line(p,q):add.append(f'(gr_line (start {p[0]} {p[1]}) (end {q[0]} {q[1]}) (stroke (width .05) (type default)) (layer "Edge.Cuts") (uuid "{uid()}"))')
 topx=53.317 if side=='Left' else 76.675;botx=53.316 if side=='Left' else 76.676
 line((topx,31.745),(x,54));line((x,54),(inner-sign*.5,54))
 add.append(f'(gr_arc (start {inner-sign*.5} 54) (mid {inner} 54.5) (end {inner-sign*.5} 55) (stroke (width .05) (type default)) (layer "Edge.Cuts") (uuid "{uid()}"))')
 line((inner-sign*.5,55),(x,55));line((x,55),(botx,84.19))

drop.update('f0c4851e 45e61e0e b57f7e15 0f92e152'.split())
repl=[]
for st,en,n in tops(b):
 if a.scalar(n,'uuid','')[:8] in drop:repl.append((st,en,''))
 elif n[0]=='footprint' and a.prop(n,'Reference') in newfps:repl.append((st,en,newfps[a.prop(n,'Reference')]))
b=rewrite(b,repl)
for label,x,y in [('GND',57.2,55.0),('GND',73.0,54.5),('+',56.2,85.0),('+',73.8,85.0)]:
 add.append(f'(gr_text "{label}" (at {x} {y}) (layer "F.SilkS") (uuid "{uid()}") (effects (font (size .8 .8) (thickness .12))))')
b=b.rstrip()[:-1]+'\n'+'\n'.join(add)+'\n)\n';(OUT/'stratolink.kicad_pcb').write_text(b)
# Preserve schematic nodes; only connector metadata changes.
repl=[]
for st,en,n in tops(s):
 if n[0]=='symbol' and a.prop(n,'Reference') in fplib:
  ref=a.prop(n,'Reference');part=s[st:en];part=re.sub(r'(\(property "Footprint" )"[^"]*"',r'\g<1>'+json.dumps(fplib[ref]),part);part=re.sub(r'(\(property "Value" )"[^"]*"',r'\g<1>"Solar panel direct solder"',part);part=re.sub(r'(\(property "Datasheet" )"[^"]*"',r'\g<1>""',part);part=re.sub(r'(\(property "Description" )"[^"]*"',r'\g<1>""',part);part=part.replace('(in_bom yes)','(in_bom no)');repl.append((st,en,part))
s=rewrite(s,repl);(OUT/'stratolink.kicad_sch').write_text(s)
(HERE/'candidate_build.json').write_text(json.dumps({'base':BASE,'candidate':str(OUT),'removed_uuid_prefixes':sorted(drop),'footprints':fplib,'added_object_count':len(add)},indent=2)+'\n')
print(OUT)
