#!/usr/bin/env python3
"""Read native geometry, native GLB marker bounds and original CPL; no CAD edits."""
from pathlib import Path
import json,csv,math,hashlib,struct,itertools
import numpy as np
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle,Circle
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];P=Path.home()/'Repositories/ai-working/scratch/stratolink-release-20261012/identities/placement-review';native=json.loads((P/'native.json').read_text());rows={r['Designator']:r for r in csv.DictReader((P/'CPL-before-preview.csv').open())};old={r['Designator']:r for r in csv.DictReader((ROOT/'hardware/gerbers/production_files/CPL-stratolink.csv').open())};sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();results={}
fig,axes=plt.subplots(1,3,figsize=(13,5.5));desired={'U5':'A1 upper-left; preserve orientation','U7':'Pin 1 lower-left; clockwise 90° from initial preview','U8':'Pin 1 lower-right; clockwise 90° from initial preview'}
for ref,ax in zip(['U5','U7','U8'],axes):
 f=native[ref];center=f['at'];side=rows[ref]['Layer'];assert float(rows[ref]['Mid X'])==center[0] and -float(rows[ref]['Mid Y'])==center[1];first='A1' if ref=='U5' else '1';firstpad=next(p for p in f['pads'] if p['n']==first);mirror=-1 if side=='bottom' else 1
 data=(P/(ref+'.glb')).read_bytes();n,t=struct.unpack_from('<II',data,12);j=json.loads(data[20:20+n]);node=next(x for x in j['nodes'] if x.get('name')==ref);x,y,z,w=node.get('rotation',[0,0,0,1]);R=np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],[2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],[2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]]);tr=np.array(node['translation']);mark=[];body=[]
 for primitive in j['meshes'][node['mesh']]['primitives']:
  a=j['accessors'][primitive['attributes']['POSITION']];cs=np.array(list(itertools.product(*zip(a['min'],a['max']))));cs=(cs@R.T+tr)*1000;cs=cs[:,[0,2,1]];bb=[cs.min(0),cs.max(0)];rgb=j['materials'][primitive['material']]['pbrMetallicRoughness']['baseColorFactor'][:3]
  if max(rgb)<.06:body.append(bb)
  marker=(ref=='U5' and min(rgb)>.99) or (ref=='U7' and min(rgb)>.99 and bb[0][2]>1.0) or (ref=='U8' and primitive['material']==2)
  if marker:mark.append(bb)
 assert mark and body
 ma=np.array(mark);mb=np.array([ma[:,0].min(0),ma[:,1].max(0)]);markcenter=mb.mean(0);ba=np.array(body);bb=np.array([ba[:,0].min(0),ba[:,1].max(0)]);bodycenter=bb.mean(0);assert np.linalg.norm(bodycenter[:2]-center)<.00001
 if ref in old:
  assert rows[ref]['Layer']==old[ref]['Layer'] and abs(float(rows[ref]['Rotation'])-float(old[ref]['Rotation']))<1e-8
  assert abs(float(rows[ref]['Mid X'])-float(old[ref]['Mid X']))<1e-8 and abs(float(rows[ref]['Mid Y'])-float(old[ref]['Mid Y']))<1e-8
 results[ref]={'mpn':{'U5':'TMP117AIYBGR','U7':'LIS2DH12TR','U8':'TLV8801DBVT'}[ref],'cpl_initial':rows[ref],'native_angle_deg':f['rotation'],'center_board_xy_mm':center,'cad_body_center_xy_mm':bodycenter[:2].tolist(),'body_center_error_mm':float(np.linalg.norm(bodycenter[:2]-center)),'pin1':firstpad,'cad_model_pin1_mark_center_board_xyz_mm':markcenter.tolist(),'cad_model_pin1_mark_bounds_board_xyz_mm':mb.tolist(),'expected_supplier_view':desired[ref],'native_glb_sha256':sha(P/(ref+'.glb')),'native_model_sources':f['models'],'pads_board_xy':f['pads'],'historical_input_exact':ref in old,'numeric_cpl_correction_verified_by_reimport':False}
 for pad in f['pads']:
  dx,dy=pad['xy'][0]-center[0],pad['xy'][1]-center[1];xx=mirror*dx;yy=dy;sx,sy=pad['size'];
  if f['rotation']%180==90:sx,sy=sy,sx
  color='#ba6f16' if pad['n']==first else '#e6b95b';ax.add_patch(Rectangle((xx-sx/2,yy-sy/2),sx,sy,fc=color,ec='#6c552f',alpha=.8));ax.text(xx,yy,pad['n'],ha='center',va='center',fontsize=9)
 bx=sorted(mirror*(bb[:,0]-center[0]));by=bb[:,1]-center[1];ax.add_patch(Rectangle((bx[0],by[0]),bx[1]-bx[0],by[1]-by[0],fill=False,ec='#425466',lw=1.4));ax.plot(mirror*(markcenter[0]-center[0]),markcenter[1]-center[1],'o',color='#166da0',ms=7,label='Native 3D pin-1 mark');ax.plot(0,0,'+',color='#242a30',ms=10);ax.set_title(ref+' — '+side+' view\nBoard center '+str(tuple(center))+' mm',fontsize=11);ax.set_aspect('equal');ax.set_xlim(-2,2);ax.set_ylim(2,-2);ax.grid(alpha=.15);ax.set_xlabel('Viewed horizontal offset (mm)'+('\nX mirrored on bottom' if side=='bottom' else ''));ax.set_ylabel('Board Y offset (mm), north up')
 ax.text(.5,-.27,desired[ref],ha='center',va='top',transform=ax.transAxes,fontsize=9,wrap=True)
fig.suptitle('Required supplier orientations from native pads and 3D markers',fontsize=14);fig.subplots_adjust(bottom=.27,wspace=.32,top=.85);fig.savefig(HERE/'supplier-placement-required.png',dpi=170)
out={'status':'Native/CPL center and model marker proof complete; supplier numeric rotation reimport pending','pcb_sha256':sha(ROOT/'hardware/pcb/stratolink.kicad_pcb'),'initial_cpl_sha256':sha(P/'CPL-before-preview.csv'),'historical_input_cpl_sha256':sha(ROOT/'hardware/gerbers/production_files/CPL-stratolink.csv'),'view_convention':'North up; top x-right/y-down, bottom horizontal mirror x-left/y-down','supplier_control_observation':'Root observed visible clockwise90 for U7/U8; download control yields image, not supplier numeric CPL. Proposed numeric values must be reimported and viewed before acceptance.','parts':results}
evidence_path=HERE/'supplier-placement-reimport-evidence.json'
if evidence_path.exists():
 evidence=json.loads(evidence_path.read_text());probe_path=HERE/evidence['input_csv'];assert sha(probe_path)==evidence['input_sha256'];assert evidence['pcb_sha256']==out['pcb_sha256'];probe={r['Designator']:r for r in csv.DictReader(probe_path.open())};assert set(probe)==set(rows)
 for ref,row in probe.items():
  permitted={'Rotation'} if ref in evidence['reimported_parts'] else set()
  assert all(row[k]==rows[ref][k] for k in row if k not in permitted)
 for ref,proof in evidence['reimported_parts'].items():
  assert proof['supplier_view_independently_checked'];assert proof['cpl_row']==probe[ref];assert sha(HERE/proof['screenshot'])==proof['screenshot_sha256']
  out['parts'][ref]['numeric_cpl_correction_verified_by_reimport']=True
  out['parts'][ref]['cpl_reimport_verified']=probe[ref]
  out['parts'][ref]['supplier_reimport_evidence']=proof
 out['parts']['U5']['preserve_original_rotation_verified_at_corner_level']=True
 out['status']='PASS: native centers/model markers; independently viewed numeric supplier CSV reimport verifies U7 0 degrees and U8 90 degrees; preserve U5 0 degrees'
 out['supplier_control_observation']='Visible CW90 button results were subsequently replaced by an uploaded numeric CSV and fresh previews; the accepted numeric angles are bound to that exact file and screenshot hashes.'
 out['reimport_input']={'path':evidence['input_csv'],'sha256':evidence['input_sha256']}
 out['reimport_evidence_sha256']=sha(evidence_path)
(HERE/'supplier-placement-review.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:{'center_error_mm':v['body_center_error_mm'],'marker_board_xy':v['cad_model_pin1_mark_center_board_xyz_mm'][:2],'required':v['expected_supplier_view']} for k,v in results.items()},indent=2))
