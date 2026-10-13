"""Deterministic two-layer grid route proposal, followed by native DRC review.

Uses native extracted copper polygons as obstacles. This is a candidate router,
not a replacement for KiCad's final connectivity, clearance and drill checks.
"""
from pathlib import Path
import json,math,heapq,uuid,time
import numpy as np
from shapely.geometry import Polygon,Point,LineString
from shapely.ops import unary_union
from shapely import contains_xy
HERE=Path(__file__).resolve().parent
DIR=Path.home()/'Repositories/ai-working/scratch/stratolink-release-20261012/power'
G=json.loads((DIR/'route-geometry.json').read_text())
G['pads']['VBAT_ANY']=dict(at=[61.375,46.207],net='/VBAT',layers=['B.Cu'])
G['pads']['GND_STITCH']=dict(at=[54.264,33.665],net='GND',layers=['B.Cu'])
G['pads']['GND_D3_VIA']=dict(at=[59.083,38.185],net='GND',layers=['F.Cu'])
G['pads']['GND_OLD_VIA']=dict(at=[58.322,49.346],net='GND',layers=['B.Cu'])
G['pads']['GND_LOWER_ZONE']=dict(at=[58.322,50.7],net='GND',layers=['B.Cu'])
G['pads']['GND_J4_ZONE']=dict(at=[74.3,68.8],net='GND',layers=['B.Cu'])
G['pads']['J4.1']['layers']=['B.Cu']
LAY=['F.Cu','B.Cu'];STEP=.05;MINX=53.2;MINY=30.2;MAXX=76.7;MAXY=86.8
xs=np.round(np.arange(MINX,MAXX+STEP/2,STEP),5);ys=np.round(np.arange(MINY,MAXY+STEP/2,STEP),5)
X,Y=np.meshgrid(xs,ys);NY,NX=X.shape
def poly(v):return unary_union([Polygon(p['shell'],p['holes']) for p in v])
items=[dict(x,shape=poly(x['polygons'])) for x in G['items']]
edge=poly(G['outline']);padarea=unary_union([x['shape'] for x in items if x['kind']=='pad']).buffer(.12)
holearea=unary_union([Point(*h['at']).buffer(h['radius']+.15+.25+.005) for h in G['holes']])
routes=[]
def nearest(p):return (int(round((p[0]-MINX)/STEP)),int(round((p[1]-MINY)/STEP)))
def world(n):return [round(float(xs[n[0]]),5),round(float(ys[n[1]]),5)]
def astar(start,goal,free,vfree,starts=None):
 np.savez(DIR/'route-debug.npz',free=free,vfree=vfree,start=np.array([*start[0],start[1]]),goal=np.array([*goal[0],goal[1]]));sx,sy=nearest(start[0]);gx,gy=nearest(goal[0]);s=(sx,sy,start[1]);end=(gx,gy,goal[1]);assert free[s[2],sy,sx],('start obstructed',start);assert free[end[2],gy,gx],('end obstructed',goal)
 def h(n):return math.hypot(n[0]-gx,n[1]-gy)+(80 if n[2]!=end[2] else 0)
 seeds=starts or [s];heap=[(h(seed),0,seed) for seed in seeds];heapq.heapify(heap);best={seed:0 for seed in seeds};parent={};count=0
 while heap:
  f,g,u=heapq.heappop(heap)
  if best.get(u)!=g:continue
  if u==end:
   path=[u]
   while u in parent:u=parent[u];path.append(u)
   return path[::-1],count
  count+=1
  if count>1800000:break
  x,y,z=u
  for dx,dy in [(1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)]:
   nx,ny=x+dx,y+dy
   if nx<0 or nx>=NX or ny<0 or ny>=NY or not free[z,ny,nx]:continue
   if dx and dy and (not free[z,y,nx] or not free[z,ny,x]):continue
   v=(nx,ny,z);ng=g+(1.41421356237 if dx and dy else 1)
   if ng<best.get(v,1e99):best[v]=ng;parent[v]=u;heapq.heappush(heap,(ng+h(v),ng,v))
  if vfree[y,x]:
   v=(x,y,1-z);ng=g+80
   if ng<best.get(v,1e99):best[v]=ng;parent[v]=u;heapq.heappush(heap,(ng+h(v),ng,v))
 raise RuntimeError(('no path',start,goal,count))
def route(net,first,second,width=.15):
 p,q=G['pads'][first],G['pads'][second];assert p['net']==q['net']==net,(net,p,q)
 available=edge.buffer(-(.2+width/2));inside=contains_xy(available,X,Y)
 free=[];obstacles=[]
 for layer in LAY:
  obs=unary_union([i['shape'] for i in items if i['layer']==layer and i['net']!=net]);obstacles.append(obs)
  foreignholes=unary_union([Point(*h['at']).buffer(h['radius']+(.28 if '.' in h['name'] else .25)+width/2+.005) for h in G['holes'] if not any(i['kind'] in ['via','pad'] and i['name']==h['name'] and i['net']==net for i in items)])
  free.append(inside & ~contains_xy(unary_union([obs.buffer(.155+width/2),foreignholes]),X,Y))
 free=np.stack(free)
 vobs=unary_union(obstacles).buffer(.405)
 viaholes=unary_union([Point(*h['at']).buffer(h['radius']+.15+.25+.005) for h in G['holes']]);vfree=contains_xy(edge.buffer(-.455),X,Y)&~contains_xy(unary_union([vobs,viaholes,padarea]),X,Y)
 start=(p['at'],LAY.index(p['layers'][0]));goal=(q['at'],LAY.index(q['layers'][0]));seeds=None
 if first=='VBAT_ANY':
  seeds=[]
  for zi,layer in enumerate(LAY):
   connected=unary_union([i['shape'] for i in items if i['layer']==layer and i['net']==net and i.get('name','').split('.')[0] not in ['U8','C22','R24']]);yy,xx=np.where(free[zi]&contains_xy(connected.buffer(-.005),X,Y));seeds.extend((int(x),int(y),zi) for y,x in zip(yy,xx))
  assert seeds
 path,count=astar(start,goal,free,vfree,seeds)
 # Collapse straight runs while preserving bends and all layer changes.
 compact=[path[0]]
 for i in range(1,len(path)-1):
  a,b,c=path[i-1:i+2]
  if tuple(b[k]-a[k] for k in range(3))!=tuple(c[k]-b[k] for k in range(3)):compact.append(b)
 compact.append(path[-1]);pts=[(world(n),n[2]) for n in compact]
 if first!='VBAT_ANY' and pts[0][0]!=p['at']:pts.insert(0,(p['at'],pts[0][1]))
 if pts[-1][0]!=q['at']:pts.append((q['at'],pts[-1][1]))
 segs=[];vias=[]
 for (a,z),(b,zz) in zip(pts,pts[1:]):
  if z!=zz:
   assert a==b;vias.append(a)
   for l in LAY:items.append(dict(kind='via',name='new-'+str(len(items)),net=net,layer=l,shape=Point(*a).buffer(.25)))
   G['holes'].append(dict(at=a,radius=.15,name='new-hole'))
  elif a!=b:
   segs.append(dict(start=a,end=b,layer=LAY[z],width=width));items.append(dict(kind='track',net=net,layer=LAY[z],shape=LineString([a,b]).buffer(width/2)))
 result=dict(net=net,first=first,second=second,width=width,segments=segs,vias=vias,expanded=count,length_mm=sum(LineString([s['start'],s['end']]).length for s in segs));routes.append(result);print(first,second,'length',round(result['length_mm'],2),'vias',len(vias),'expanded',count,flush=True)
def main():
 pairs=[('/VBAT','VBAT_ANY','U8.5'),('/SC_MID','C5.3','R26.2'),('/SC_BAL_OUT','U8.1','U8.4'),('/SC_HALF_REF','U8.3','R24.2'),('/SC_HALF_REF','R24.2','R25.1'),('/VBAT','U8.5','C22.1'),('/VBAT','U8.5','R24.1'),('/SC_BAL_OUT','U8.1','R26.1'),('VSTOR','R22.1','J4.2'),('GND','U8.2','GND_STITCH'),('GND','C22.2','U8.2'),('GND','R25.2','GND_STITCH'),('GND','D3.1','GND_D3_VIA'),('GND','J4.1','GND_J4_ZONE')]
 for net,p,q in pairs:
  (DIR/'routes-partial.json').write_text(json.dumps(routes,indent=2)+'\n')
  route(net,p,q)
 (DIR/'routes.json').write_text(json.dumps(routes,indent=2)+'\n')
 s=(DIR/'balancer-unrouted.kicad_pcb').read_text();added=[];ns=uuid.UUID('5fc6d07c-09de-4f36-b967-0f0787894718')
 for ri,r in enumerate(routes):
  for i,t in enumerate(r['segments']):added.append('(segment (start %s %s) (end %s %s) (width %s) (layer "%s") (net "%s") (uuid "%s"))'%(*t['start'],*t['end'],t['width'],t['layer'],r['net'],uuid.uuid5(ns,f'{ri}-seg-{i}')))
  for i,at in enumerate(r['vias']):added.append('(via (at %s %s) (size 0.5) (drill 0.3) (layers "F.Cu" "B.Cu") (net "%s") (uuid "%s"))'%(*at,r['net'],uuid.uuid5(ns,f'{ri}-via-{i}')))
 (DIR/'balancer-candidate/stratolink.kicad_pcb').write_text(s[:s.rfind(')')]+'\n'+'\n'.join(added)+'\n)\n')
 print('Complete proposal',len(added),'objects',flush=True)
if __name__=='__main__':main()
