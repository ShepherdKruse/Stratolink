import math
from shapely.geometry import LineString
# Trace arc centerline via circumcircle through start/mid/end, with native length enforcing sweep.
def path(t):
 a=t['start'];b=t['end']
 if t['kind']!='PCB_ARC':return LineString([a,b])
 m=t['mid'];D=2*(a[0]*(m[1]-b[1])+m[0]*(b[1]-a[1])+b[0]*(a[1]-m[1]));A=a[0]**2+a[1]**2;M=m[0]**2+m[1]**2;B=b[0]**2+b[1]**2;cx=(A*(m[1]-b[1])+M*(b[1]-a[1])+B*(a[1]-m[1]))/D;cy=(A*(b[0]-m[0])+M*(a[0]-b[0])+B*(m[0]-a[0]))/D;r=math.dist(a,[cx,cy]);th=math.atan2(a[1]-cy,a[0]-cx);end=math.atan2(b[1]-cy,b[0]-cx);mid=math.atan2(m[1]-cy,m[0]-cx);delta=(end-th)%(2*math.pi)
 if (mid-th)%(2*math.pi)>delta+1e-6:delta-=2*math.pi
 return LineString([(cx+r*math.cos(th+delta*i/64),cy+r*math.sin(th+delta*i/64))for i in range(65)])
