"""Analytic segment-to-triangle minimum distance in millimetres."""
import numpy as np
# Exact segment/segment closest points, Ericson region clamping.
def segdist(a,b,c,d):
 u=b-a;v=d-c;w=a-c;A=u@u;B=u@v;C=v@v;D=u@w;E=v@w;den=A*C-B*B
 if A<1e-20:return np.linalg.norm(a-(c+np.clip(E/C if C else 0,0,1)*v))
 if C<1e-20:return np.linalg.norm(c-(a+np.clip(-D/A,0,1)*u))
 s=np.clip((B*E-C*D)/den,0,1) if den>1e-20 else 0;t=(B*s+E)/C
 if t<0:t=0;s=np.clip(-D/A,0,1)
 elif t>1:t=1;s=np.clip((B-D)/A,0,1)
 return np.linalg.norm(w+s*u-t*v)
def intriangle(p,a,b,c):
 v0=b-a;v1=c-a;v2=p-a;aa=v0@v0;bb=v0@v1;cc=v1@v1;dd=v2@v0;ee=v2@v1;den=aa*cc-bb*bb
 if den<1e-24:return False
 u=(cc*dd-bb*ee)/den;v=(aa*ee-bb*dd)/den;return u>=-1e-10 and v>=-1e-10 and u+v<=1+1e-10
def triseg(p,q,a,b,c):
 n=np.cross(b-a,c-a);norm=np.linalg.norm(n)
 if norm<1e-12:return min(segdist(p,q,a,b),segdist(p,q,b,c),segdist(p,q,c,a))
 n=n/norm;dp=(p-a)@n;dq=(q-a)@n;result=min(segdist(p,q,a,b),segdist(p,q,b,c),segdist(p,q,c,a))
 for e,de in [(p,dp),(q,dq)]:
  foot=e-de*n
  if intriangle(foot,a,b,c):result=min(result,abs(de))
 if dp*dq<=0 and abs(dp-dq)>1e-12:
  x=p+(q-p)*dp/(dp-dq)
  if intriangle(x,a,b,c):result=0
 return result
