"""Small read-only KiCad S-expression geometry helpers; no file mutations."""
import re
import json
import math

def parse(text):
    tokens=re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+',text)
    stack=[]; root=None
    for t in tokens:
        if t=='(':
            a=[]
            if stack:stack[-1].append(a)
            else:root=a
            stack.append(a)
        elif t==')':stack.pop()
        else:
            if t.startswith('"'):t=json.loads(t)
            stack[-1].append(t)
    assert not stack
    return root
def nodes(o,key):return [x for x in o if isinstance(x,list) and x and x[0]==key]
def one(o,key,default=None):
    n=nodes(o,key);return n[0][1:] if n else default
def scalar(o,key,default=None):
    n=one(o,key);return n[0] if n else default
def floats(o,key,default=None):
    v=one(o,key);return list(map(float,v)) if v else default
def prop(o,key):
    return next((x[2] for x in nodes(o,'property') if x[1]==key),None)
def point_global(fp,p):
    at=floats(fp,'at'); x,y=p[:2];r=math.radians(at[2] if len(at)>2 else 0)
    return [at[0]+x*math.cos(r)+y*math.sin(r),at[1]-x*math.sin(r)+y*math.cos(r)]
