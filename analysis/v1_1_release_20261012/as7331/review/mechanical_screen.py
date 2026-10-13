#!/usr/bin/env python3
"""Conservative package-outline checks, not suspension-string qualification."""
import argparse,hashlib,json,math
from pathlib import Path
import pcbnew,wx
HERE=Path(__file__).resolve().parent

def xy(p):return [p.x/1e6,p.y/1e6]
def box(center,size):return [center[0]-size[0]/2,center[1]-size[1]/2,center[0]+size[0]/2,center[1]+size[1]/2]
def sep(a,b):return math.hypot(max(a[0]-b[2],b[0]-a[2],0),max(a[1]-b[3],b[1]-a[3],0))
def point_box(p,b):return math.hypot(max(b[0]-p[0],p[0]-b[2],0),max(b[1]-p[1],p[1]-b[3],0))
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--pcb',type=Path,required=True);a=ap.parse_args();app=wx.App(False);b=pcbnew.LoadBoard(str(a.pcb));f={x.GetReference():x for x in b.GetFootprints()}
    assert f['U6'].GetOrientationDegrees()%180==0 and f['R27'].GetOrientationDegrees()%90==0
    u6=box(xy(f['U6'].GetPosition()),[2.7,3.75]);r27size=[2.1,1.4] if f['R27'].GetOrientationDegrees()%180==0 else [1.4,2.1];r27=box(xy(f['R27'].GetPosition()),r27size);u5=box(xy(f['U5'].GetPosition()),[.98,1.518]);courtyards={}
    for ref in ['U7','U5','C14','C23']:
        parts=[g.GetBoundingBox() for g in f[ref].GraphicalItems() if g.GetLayer()==pcbnew.F_CrtYd]
        if parts:courtyards[ref]=[min(p.GetLeft() for p in parts)/1e6,min(p.GetTop() for p in parts)/1e6,max(p.GetRight() for p in parts)/1e6,max(p.GetBottom() for p in parts)/1e6]
    h2=next(iter(f['H2'].Pads()));hc=xy(h2.GetPosition());hr=h2.GetSize().x/2e6;hole=h2.GetDrillSize().x/2e6
    rp=next(p for p in f['R27'].Pads() if p.GetNumber()=='1');rr=rp.GetRoundRectCornerRadius()/1e6;rs=xy(rp.GetSize());rs=rs if rp.GetOrientationDegrees()%180==0 else rs[::-1];rc=xy(rp.GetPosition());core=box(rc,[rs[0]-2*rr,rs[1]-2*rr])
    underbody=[]
    for v in b.GetTracks():
        if not isinstance(v,pcbnew.PCB_VIA):continue
        vc=xy(v.GetPosition());vr=v.GetWidth(pcbnew.F_Cu)/2e6
        if point_box(vc,u6)>vr:continue
        nearest=[]
        for pad in f['U6'].Pads():
            pc=xy(pad.GetPosition());nearest.append((point_box(vc,box(pc,[.35,.35]))-vr,pad.GetNumber(),point_box(vc,box(pc,[.3,.3]))-vr))
        distance,pin,paste=min(nearest)
        underbody.append(dict(uuid=v.m_Uuid.AsString(),net=v.GetNetname(),at_mm=vc,diameter_mm=2*vr,drill_mm=v.GetDrillValue()/1e6,minimum_annulus_to_u6_land_mm=distance,nearest_u6_pin=pin,annulus_to_that_paste_mm=paste,tented_front=bool(v.IsTented(pcbnew.F_Mask)),tented_back=bool(v.IsTented(pcbnew.B_Mask))))
    overlap=[min(u6[2],r27[2])-max(u6[0],r27[0]),min(u6[3],r27[3])-max(u6[1],r27[1])]
    result=dict(status='FAIL_BODY_OVERLAP' if min(overlap)>0 else 'PASS_OUTLINE_SCREEN',vias_touching_max_u6_body=underbody,u6_to_r27_max_bodies_mm=sep(u6,r27),u6_r27_signed_axis_overlap_mm=overlap,pcb_sha256=hashlib.sha256(a.pcb.read_bytes()).hexdigest(),u6_max_body_mm=u6,r27_max_body_mm=r27,u5_max_body_mm=u5,u6_to_u5_max_bodies_mm=sep(u6,u5),u6_to_neighbor_courtyard_AABB_lower_bounds_mm={r:sep(u6,c) for r,c in courtyards.items()},r27_to_h2_hole_maxbody_mm=point_box(hc,r27)-hole,r27_to_h2_copper_maxbody_mm=point_box(hc,r27)-hr,r27_rext_pad_to_h2_copper_mm=point_box(hc,core)-rr-hr,notes=['U6 maximum 2.7×3.75 mm from DS001047; R27 maximum2.1×1.4mm from Vishay28952; U5max0.98×1.518mm from TI YBG0006-C01.','AABB distances can understate actual separation; dimensions do not include PCB feature tolerance, placement error, or solder fillets.','Ceramic body overlap above a grounded mounting annulus is not by itself an electrical short.','Only the known hole and component geometry is tested. The triangular stretchy string has unknown diameter and trajectory; actual lashing, panel bends and future optics require fit check.'])
    (HERE/'mechanical-screen.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
