from pathlib import Path
import json,math,heapq
import numpy as np
from shapely.geometry import Polygon,Point,LineString,box
from shapely.ops import unary_union
import shapely
HERE=Path(__file__).resolve().parent;d=json.loads((HERE/'native-rf-geometry.json').read_text())
RF='Net-(AE2-A)'
def geom(i):return unary_union([Polygon(p['shell'],p['holes'])for p in i['polygons']])
front=[];back=[]
for i in d['items']:
 if i['net']in[RF,'/SC_MID'] or i['kind']=='zone':continue
 g=geom(i)
 if i['layer']=='F.Cu' and not(i['net']=='GND' and i['kind'] in ['PCB_TRACK','PCB_VIA']):front.append(g)
 elif i['net'] in ['Net-(U1-LBOOST)','Net-(U1-LBUCK)']:back.append(g)
front.append(LineString([(59.75,41.15),(59.75,43.05),(59.1,43.7)]).buffer(.075))
front += [Point(x,y).buffer(.25) for x,y in [(59.75,41.15),(59.1,43.7),(57.75,45.6)]]
f=unary_union(front);b=unary_union(back)
width=.75; step=.05;xmin,ymin,xmax,ymax=53.6,29.6,76.3,46.1
xs=np.arange(xmin,xmax+step/2,step);ys=np.arange(ymin,ymax+step/2,step)
pts=shapely.points(*np.meshgrid(xs,ys));obs=f.buffer(width/2+.15).union(b.buffer(width/2+.50));blocked=shapely.contains(obs,pts)
# Exact endpoints are RF pad centers; nearest grid nodes otherwise.
s0=(60.787001,45.114001);goal0=(62.882,33.218)
def idx(p):return(round((p[1]-ymin)/step),round((p[0]-xmin)/step))
s=idx(s0);goal=idx(goal0);print('blocked endpoints',blocked[s],blocked[goal]);q=[(0,s)];dist={s:0};prev={}
while q:
 _,u=heapq.heappop(q)
 if u==goal:break
 for dy,dx in [(0,1),(1,0),(0,-1),(-1,0),(1,1),(1,-1),(-1,1),(-1,-1)]:
  v=(u[0]+dy,u[1]+dx)
  if not(0<=v[0]<len(ys)and 0<=v[1]<len(xs))or blocked[v]:continue
  cost=dist[u]+math.hypot(dx,dy)*step
  if cost<dist.get(v,1e9):
   dist[v]=cost;prev[v]=u;heapq.heappush(q,(cost+math.hypot(v[0]-goal[0],v[1]-goal[1])*step,v))
if goal in dist:
 path=[goal];u=goal
 while u!=s:u=prev[u];path.append(u)
 path.reverse();coords=[(xs[i[1]],ys[i[0]])for i in path];simple=list(LineString(coords).simplify(.03).coords)
 print('length',dist[goal]);print(simple)
 (HERE/'route-screen.json').write_text(json.dumps(dict(width=width,step=step,path=simple,length=dist[goal]),indent=2)+'\n')
else:print('NO PATH')
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
fig,ax=plt.subplots(figsize=(12,9));ax.imshow(blocked,origin='lower',extent=[xmin,xmax,ymin,ymax],cmap='Greys',alpha=.6)
reach=np.zeros_like(blocked,dtype=float)
for v in dist:reach[v]=1
ax.imshow(np.ma.masked_where(reach==0,reach),origin='lower',extent=[xmin,xmax,ymin,ymax],cmap='Blues',alpha=.5)
ax.plot(*s0,'ro');ax.plot(*goal0,'go')
if goal in dist:ax.plot(*zip(*simple),color='magenta')
ax.set_ylim(ymax,ymin);ax.grid();fig.savefig(HERE/'route-grid.png',dpi=150)
