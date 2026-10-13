#!/usr/bin/env python3
"""U7 top escape, underbody keepout and 81% nominal stencil aperture candidate."""
from pathlib import Path
import sys,json,shutil,uuid
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));import build_metadata as m
a=m.a;OUT=m.OUT.parent/'u7-candidate'
REMOVE={'3c460803-a0e0-4087-a6f3-936cf4d1fee5','50467fe8-5838-443d-bd6f-469444951d63','5dc0585a-7141-4f08-afce-4a3c96f8fc8d','6bbdefb3-9efe-4d87-82b7-4e492977fa39','84d64290-6950-4148-b45a-9ed52cbfe265','c071d5fe-1b47-46a1-bcdd-4d46cde56e79','c542a530-7aab-438f-8d70-88a1c96fa3d6','eb1489ed-e03a-4611-9a19-01ffdfe3f79b','acf3109c-eb1e-4509-9789-79a4830e3dcb','19d84636-dd1d-4c0b-826b-eb8fe3196356','a8f806ed-4e7a-4dae-9ad1-db4955088bff','66a82ae2-fcc0-482c-bf5c-4e43c7fe8847','cb3f0267-bffe-4bc8-a5fc-742f300859ce',
'3777268c-2956-4adc-8055-47eb850a79b4','4804ca70-e725-4411-8161-211cdfd420f4','5b010a5d-3cf4-4a82-a8e6-cad18abe79b0','85dff8c6-5433-4e72-8157-8dcf49f19daf','8e9a2f05-b219-4858-aef3-4548091e9031','a2699bc6-d280-43ac-8fc2-ea5a3655931b','bb51434a-165d-47a7-b603-0b2f78c2eb54','e884341a-a321-4ea4-ac9a-20b95cc49102'}
def uid(k):return str(uuid.uuid5(uuid.NAMESPACE_URL,'stratolink-v11-U7-release-'+k))
paths=[('g7','GND',.15,[(71.298,37.042),(71.298,36.65),(70.798,36.65)]),('g6','GND',.15,[(71.313,37.557),(71.9,37.557),(72.476,37.635)]),('g5','GND',.15,[(71.313,38.072),(71.6,38.072),(71.8,37.872),(71.8,37.557)]),('g3','GND',.1,[(70.798,38.572),(70.798,39.0),(72.1,39.0)]),('v2','+3.3V',.1,[(70.298,38.572),(70.298,38.95),(69.85,39.2)]),('scl','SCL',.1,[(69.798,38.571999),(69.39,38.98),(69.39,39.35),(69.5,39.49),(69.6,39.61),(69.7,39.651),(72.669,39.651),(73.171,39.149),(73.49165,39.149)])]
vias=[('g3','GND',(72.1,39.0)),('v2','+3.3V',(69.85,39.2))]

def keepout(name,box,tracks):
 x0,y0,x1,y1=box
 return f'''(zone (net "") (net_name "") (layer "F.Cu") (uuid "{uid(name)}") (name "{name}") (hatch edge 0.5) (connect_pads (clearance 0)) (min_thickness 0.25) (keepout (tracks {tracks}) (vias not_allowed) (pads allowed) (copperpour not_allowed) (footprints allowed)) (fill (thermal_gap 0.3) (thermal_bridge_width 0.3)) (polygon (pts (xy {x0} {y0}) (xy {x1} {y0}) (xy {x1} {y1}) (xy {x0} {y1}))))'''
def main():
 if OUT.exists():shutil.rmtree(OUT)
 shutil.copytree(m.OUT,OUT)
 p=OUT/'stratolink.kicad_pcb';text=p.read_text();ed=[];removed=[]
 for s,e,d in m.m.spans(text):
  if d!=1:continue
  n=a.parse(text[s:e]);ident=a.scalar(n,'uuid')
  if n[0]=='zone':
   z=text[s:e];ze=[]
   for zs,zend,zd in m.m.spans(z):
    if zd==1 and a.parse(z[zs:zend])[0] in {'filled_polygon','filled_areas_thickness'}:ze.append((zs,zend,''))
   if ze:ed.append((s,e,m.m.replace(z,ze)))
  if n[0]=='segment' and ident in REMOVE:ed.append((s,e,''));removed.append(ident)
  if n[0]=='footprint' and a.prop(n,'Reference')=='U7':
   f=text[s:e];ped=[]
   for ps,pe,pd in m.m.spans(f):
    if pd==1:
     pn=a.parse(f[ps:pe])
     if pn[0]=='pad' and pn[1] in {'3','6'}:
      assert a.one(pn,'zone_connect') is None
      ped.append((ps,pe,f[ps:pe-1]+' (zone_connect 0))'))
   f=m.m.replace(f,ped);f=f[:-1]+' (solder_paste_margin_ratio -0.05)\n)';ed.append((s,e,f))
 assert set(removed)==REMOVE
 text=m.m.replace(text,ed);addition=[]
 for key,net,width,points in paths:
  for i,(p0,p1) in enumerate(zip(points,points[1:])):addition.append(f'(segment (start {p0[0]} {p0[1]}) (end {p1[0]} {p1[1]}) (width {width}) (layer "F.Cu") (net "{net}") (uuid "{uid(key+str(i))}"))')
 for key,net,pt in vias:addition.append(f'(via (at {pt[0]} {pt[1]}) (size 0.5) (drill 0.3) (layers "F.Cu" "B.Cu") (net "{net}") (uuid "{uid(key+"via")}"))')
 addition.append(f'(segment (start 69.85 39.2) (end 70.956 39.540998) (width 0.2) (layer "B.Cu") (net "+3.3V") (uuid "{uid("v2-back")}"))')
 addition.append(keepout('U7 MEMS body - no top fill or vias',(69.473,36.732,71.623,38.882),'allowed'))
 addition.append(keepout('U7 MEMS central area - no top routes',(70.008,37.267,71.088,38.347),'not_allowed'))
 p.write_text(text.rstrip()[:-1]+'\n'+'\n'.join(addition)+'\n)\n')
 (HERE/'u7-build.json').write_text(json.dumps(dict(candidate=str(OUT),metadata_base=str(m.OUT),removed_segments=sorted(REMOVE),paths=paths,vias=vias,keepouts=[uid('U7 MEMS body - no top fill or vias'),uid('U7 MEMS central area - no top routes')],paste_ratio=-.05,zone_connect_zero=['3','5','6','7','8']),indent=2)+'\n')
 print(OUT)
if __name__=='__main__':main()
