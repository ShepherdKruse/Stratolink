"""Conservative grid search proposes isolated UV branches; native DRC is authority."""
from pathlib import Path
from PIL import Image,ImageDraw
import numpy as np, scipy.ndimage as ndi,math,json,heapq,uuid
HERE=Path(__file__).resolve().parent;OUT=Path.home()/'Repositories/ai-working/scratch/stratolink-release-20261012/as7331/candidate';r=json.loads((HERE/'unrouted-geometry.json').read_text())
STEP=.025;X0,Y0=65.,29.4;X1,Y1=76.30,44.5;NX=int(round((X1-X0)/STEP))+1;NY=int(round((Y1-Y0)/STEP))+1
# Extra 0.04mm raster safety is budgeted beyond0.15required spacing.
CLEAR=.1525;WIDTH=.12;VR=.25
routes=[]
def grid(p):return (round((p[0]-X0)/STEP),round((p[1]-Y0)/STEP))
def mm(p):return [round(X0+p[0]*STEP,6),round(Y0+p[1]*STEP,6)]
def mask(net,via=False):
 ims=[Image.new('1',(NX,NY)) for _ in range(2)];draw=[ImageDraw.Draw(i) for i in ims]
 grow=(VR if via else WIDTH/2)+CLEAR
 def capsule(d,s,e,rad):
  ss,ee=grid(s),grid(e);rr=rad/STEP;d.line([ss,ee],fill=1,width=math.ceil(rr*2)+1)
  for x,y in [ss,ee]:d.ellipse((x-rr,y-rr,x+rr,y+rr),fill=1)
 for t in r['tracks']:
  if t['net']==net and not(via and t['via']):continue
  layers=[0,1] if t['via'] else [0 if t['side']=='F.Cu' else 1]
  rad=t['width']/2+grow
  if via and t['via']:rad=max(rad,.65)
  for l in layers:capsule(draw[l],t['s'],t['e'],rad)
 for p in r['pads']:
  if p['net']==net and not via:continue
  layers=[0,1] if p['pth'] else [0 if p['side']=='F.Cu' else 1]
  w,h=p['size'];x,y=p['at'];rad=math.radians(p['angle']);c,s=math.cos(rad),math.sin(rad)
  pts=[grid((x+u*c+v*s,y-u*s+v*c)) for u,v in [(-w/2,-h/2),(w/2,-h/2),(w/2,h/2),(-w/2,h/2)]]
  for l in layers:
   draw[l].polygon(pts,fill=1)
   for p0,p1 in zip(pts,pts[1:]+pts[:1]):capsule(draw[l],mm(p0),mm(p1),grow)
 # MEMS front centralkeepout and prohibit new vias within known GNSSmodulebody.
 # Front routing inside old-module projected body is avoided for all new branches.
 for l in ([0,1] if via else [0]):
  draw[l].rectangle([grid((60.587,42.964)),grid((70.487,53.564))],fill=1)
  draw[l].rectangle([grid((70.008,37.267)),grid((71.088,38.347))],fill=1)
 # Preserve GNSS RF return; no new trace/via under its long feed.
 for l in ([0,1] if via else [1]):draw[l].rectangle([grid((60.3,32)),grid((64.2,45.6))],fill=1)
 return np.stack([np.asarray(i,dtype=bool) for i in ims])
def route(net,start,end,name,front_only=False,width=.15,start_layer=0,end_layer=0):
 global WIDTH
 WIDTH=width
 blocked=mask(net);vias=mask(net,True);vfree=~vias.any(axis=0)
 old_vias={grid(t['s']) for t in r['tracks'] if t['via'] and t['net']==net}
 for xx,yy in old_vias:
  if 0<=xx<NX and 0<=yy<NY:vfree[yy,xx]=True
 a=(*grid(start),start_layer);z=(*grid(end),end_layer)
 for xx,yy,l in [a,z]:
  assert 0<=xx<NX and 0<=yy<NY
  # Endpoint may be on existing-net pad center; never clearforeignobstacles.
  if blocked[l,yy,xx]:print('BLOCKED endpoint',name,mm((xx,yy)),flush=True)
 dist={a:0};prev={};heap=[(0,a)];seen=set();D=[(1,0,1),(-1,0,1),(0,1,1),(0,-1,1),(1,1,1.414),(-1,1,1.414),(1,-1,1.414),(-1,-1,1.414)]
 while heap:
  _,u=heapq.heappop(heap)
  if u in seen:continue
  seen.add(u)
  if u==z:break
  x,y,l=u
  options=[((x+dx,y+dy,l),cost) for dx,dy,cost in D]
  if not front_only and vfree[y,x]:options.append(((x,y,1-l),45))
  for v,cost in options:
   xx,yy,ll=v
   if not(0<=xx<NX and 0<=yy<NY) or blocked[ll,yy,xx]:continue
   if ll==l and xx!=x and yy!=y and (blocked[l,y,xx] or blocked[l,yy,x]):continue
   nd=dist[u]+cost
   if u in prev and tuple(u[k]-prev[u][k] for k in range(3))!=tuple(v[k]-u[k] for k in range(3)):nd+=.04
   if nd>=dist.get(v,1e20):continue
   dist[v]=nd;prev[v]=u;h=math.hypot(z[0]-xx,z[1]-yy)+(0 if ll==z[2] else 15);heapq.heappush(heap,(nd+h,v))
 else:
  for l in [0,1]:
   im=Image.fromarray((blocked[l]*255).astype('uint8')).convert('RGB');dd=ImageDraw.Draw(im)
   for x,y,ll in seen:
    if ll==l:dd.point((x,y),fill=(0,100,0))
   dd.ellipse((z[0]-3,z[1]-3,z[0]+3,z[1]+3),fill=(255,0,0));im.resize((NX*3,NY*3)).save(str(HERE/('blocked-'+name+str(l)+'.png')))
  raise RuntimeError('NO PATH '+name+' visited'+str(len(seen)))
 points=[];u=z
 while True:
  points.append(u)
  if u==a:break
  u=prev[u]
 points.reverse()
 simp=[points[0]]
 for i in range(1,len(points)-1):
  if tuple(points[i][k]-points[i-1][k] for k in range(3))!=tuple(points[i+1][k]-points[i][k] for k in range(3)):simp.append(points[i])
 simp.append(points[-1]);segs=[];via=[]
 for p0,p1 in zip(simp,simp[1:]):
  if p0[2]!=p1[2]:
   if (p0[0],p0[1]) not in old_vias:via.append(mm(p0));r['tracks'].append(dict(s=mm(p0),e=mm(p0),net=net,side='F.Cu',width=.5,via=True))
  else:
   seg=dict(s=mm(p0),e=mm(p1),net=net,side='F.Cu' if p0[2]==0 else 'B.Cu',width=WIDTH,via=False);segs.append(seg);r['tracks'].append(seg)
 # True pad endpoints areinside copper, nearest-grid endpoint keeps overlap.
 routes.append(dict(name=name,net=net,start=start,end=end,segments=segs,vias=via));(HERE/'inprogress-routes.json').write_text(json.dumps(routes,indent=2));print(name,'segments',len(segs),'vias',len(via),'length',sum(math.dist(v['s'],v['e']) for v in segs),flush=True)
pads={(p['ref'],p['n']):p['at'] for p in r['pads']}
route('+3.3V',pads['U6','3'],pads['C14','2'],'analog-bypass',True)
r['tracks'].append(dict(s=[74.025,36.85],e=[74.025,36.85],net='+3.3V',side='F.Cu',width=.5,via=True))
routes.append(dict(name='supply-tented-via',net='+3.3V',start=[74.025,36.85],end=[74.025,36.85],segments=[],vias=[[74.025,36.85]]))
for name,pt in [('sda-u7-via',[72.1,39.0]),('sda-uv-via',[73.825,37.55])]:
 r['tracks'].append(dict(s=pt,e=pt,net='SDA',side='F.Cu',width=.5,via=True));routes.append(dict(name=name,net='SDA',start=pt,end=pt,segments=[],vias=[pt]))
for name,pt,diam in [('uv-ground-via',[74.025,39.1],.4),('analog-ground-via',[72.55,36.9],.5),('u7-ground-via',[71.4,39.16],.4)]:
 r['tracks'].append(dict(s=pt,e=pt,net='GND',side='F.Cu',width=diam,via=True));routes.append(dict(name=name,net='GND',start=pt,end=pt,segments=[],vias=[pt],via_size=diam,via_drill=(.2 if diam==.4 else .3)))
route('+3.3V',pads['U6','3'],(74.025,36.85),'rail-feed-front',True)
route('+3.3V',(74.025,36.85),(70.956,39.541),'rail-feed-back',True,.15,1,1)
route('/UV_REXT',pads['U6','4'],pads['R27','1'],'reference',True)
route('+3.3V',pads['U6','10'],pads['C23','2'],'digital-bypass',True)
route('+3.3V',pads['U6','3'],pads['U6','10'],'supply-join',True)
route('VSTOR',(70.8,33.503),(76.275,33.9),'vstor-detour-top',True,.25)
route('VSTOR',(76.275,33.9),(76.275,42.6),'vstor-detour-edge',True,.25)
route('VSTOR',(76.275,42.6),(75.909911,43.0),'vstor-detour-return',True,.25)
route('PB5',(72.097,36.354),(73.4,35.9),'powergood-back-north',True,.25,1,1)
route('PB5',(73.4,35.9),(74.575,36.25),'powergood-back-east',True,.25,1,1)
route('PB5',(74.575,36.25),(75.452,41.8),'powergood-detour',False,.25,1)
route('SCL',pads['U5','A2'],(74.463,41.267386),'scl-tmp-return',True)
route('SCL',(73.171,39.149),pads['U5','A2'],'scl-local-bus')
route('SCL',pads['U6','13'],(72.669,39.651),'scl')
route('SDA',pads['U7','4'],pads['U6','12'],'sda-u7')
route('SDA',pads['U6','12'],(73.4,39.9),'sda-bus')
route('SDA',(71.35,40.05),(73.4,39.9),'sda-old-stub')
route('+3.3V',pads['C21','2'],pads['C19','2'],'c21-vdd-repair',True,.38)
route('GND',pads['C21','1'],pads['C19','1'],'c21-gnd-repair',True,.2)
for p,q,n in [('1','2','top-gnd'),('1','16','top-left-gnd'),('16','15','left-gnd-1'),('15','14','left-gnd-2')]:route('GND',pads['U6',p],pads['U6',q],n,True)
route('GND',pads['U6','14'],(72.55,36.9),'uv-analog-ground',True)
route('GND',pads['U6','11'],(74.025,39.1),'uv-digital-ground',True)
route('GND',pads['C23','1'],pads['U6','11'],'c23-ground',True)
route('GND',pads['C14','1'],pads['U6','2'],'c14-ground',True)
route('GND',pads['U7','7'],(72.55,36.9),'u7-ground-top',True)
route('GND',pads['U7','3'],(71.4,39.16),'u7-ground-bottom',True)
(HERE/'routing-proposal.json').write_text(json.dumps(routes,indent=2)+'\n')
# Append explicitnativeitems deterministicID; nativeDRCfeedbackdrives refinement.
def uid(k):return str(uuid.uuid5(uuid.NAMESPACE_URL,'stratolink-as7331-route-'+k))
add=[]
for rr in routes:
 for i,s in enumerate(rr['segments']):add.append(f'(segment (start {s["s"][0]} {s["s"][1]}) (end {s["e"][0]} {s["e"][1]}) (width {s["width"]}) (layer "{s["side"]}") (net "{s["net"]}") (uuid "{uid(rr["name"]+"seg"+str(i))}"))')
 for i,v in enumerate(rr['vias']):add.append(f'(via (at {v[0]} {v[1]}) (size {rr.get("via_size",.5)}) (drill {rr.get("via_drill",.3)}) (layers "F.Cu" "B.Cu") (net "{rr["net"]}") (uuid "{uid(rr["name"]+"via"+str(i))}"))')
p=OUT/'stratolink.kicad_pcb';t=p.read_text();p.write_text(t.rstrip()[:-1]+'\n'+'\n'.join(add)+'\n)\n')
