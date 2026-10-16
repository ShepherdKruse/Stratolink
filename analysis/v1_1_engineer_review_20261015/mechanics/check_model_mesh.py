from pathlib import Path
import struct,json,hashlib,sys
import numpy as np
p=Path(sys.argv[1]);output=Path(sys.argv[2]);pcb=Path(sys.argv[3]);raw=p.read_bytes();n,t=struct.unpack('<II',raw[12:20]);j=json.loads(raw[20:20+n]);binlen,bintype=struct.unpack('<II',raw[20+n:28+n]);buf=raw[28+n:28+n+binlen];rows=[]
for node in j['nodes']:
 if 'mesh'not in node:continue
 pts=[]
 for primitive in j['meshes'][node['mesh']]['primitives']:
  ac=j['accessors'][primitive['attributes']['POSITION']];v=j['bufferViews'][ac['bufferView']];assert ac['componentType']==5126 and ac['type']=='VEC3';start=v.get('byteOffset',0)+ac.get('byteOffset',0);pts.append(np.frombuffer(buf,dtype='<f4',count=ac['count']*3,offset=start).reshape(-1,3))
 a=np.concatenate(pts).astype(float);x,y,z,w=node['rotation'];R=np.array([[1-2*y*y-2*z*z,2*x*y-2*z*w,2*x*z+2*y*w],[2*x*y+2*z*w,1-2*x*x-2*z*z,2*y*z-2*x*w],[2*x*z-2*y*w,2*y*z+2*x*w,1-2*x*x-2*y*y]]);world=(a@R.T+node['translation'])*1000
 # In KiCad glTF output, global X/Z are board X/Y; globalY is height.
 axis=np.array([[.0001605,0,0],[.0001605,.048 if node['name']=='AE2'else .082,0]])@R.T+node['translation'];rows.append({'ref':node['name'],'local_mesh_bounds_mm':(np.r_[a.min(0),a.max(0)]*1000).tolist(),'global_bounds_mm':np.r_[world.min(0),world.max(0)].tolist(),'wire_axis_board_XY_mm':(axis[:,[0,2]]*1000).tolist(),'modeled_straight_segment_mm':48 if node['name']=='AE2' else 82})
report={'pcb_sha256':hashlib.sha256(pcb.read_bytes()).hexdigest(),'glb_sha256':hashlib.sha256(raw).hexdigest(),'models':rows,'method':'Native KiCad/OCC GLB export of AE1/AE2 STEP geometry; parsed FLOAT VEC3 positions and actual node quaternion transforms. Two-millimeter solder-tail bends retained. Model dimensions remain nominal assembly aids, not measured wire diameter.'}
output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(rows,indent=2))
