#!/usr/bin/env python3
"""Strict native-Gerber selective-mask point/distance checks (no general Gerber guessing)."""
from pathlib import Path
import argparse,hashlib,json,math,re
import pcbnew,wx

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def parse_mask(path):
    text=path.read_text()
    for token in ('%TF.FilePolarity,Negative*%','%FSLAX46Y46*%','%MOMM*%','%LPD*%'):
        assert token in text,('Unknown mask format',token)
    assert '%LPC*%' not in text,'Clear polarity requires full boolean review'
    # KiCad emits the minimum-web mask as polygon regions. Reject other forms
    # rather than silently miss an aperture or unsupported arc/transform.
    regions=[];contours=None;contour=None
    for line in text.splitlines():
        line=line.strip()
        if not line or line.startswith('G04 ') or line.startswith('%TF.'):continue
        if line in {'%FSLAX46Y46*%','%MOMM*%','%LPD*%','G01*','M02*'}:continue
        if line=='G36*':assert contours is None;contours=[];contour=None;continue
        if line=='G37*':
            assert contours is not None and contour and len(contour)>2
            contours.append(contour);regions.append(contours);contours=None;contour=None;continue
        match=re.fullmatch(r'X(-?\d+)Y(-?\d+)D0([12])\*',line)
        if match:
            assert contours is not None,'Non-region stroke'
            pt=(int(match[1])/1e6,-int(match[2])/1e6)
            if match[3]=='2':
                if contour:assert len(contour)>2;contours.append(contour)
                contour=[pt]
            else:assert contour is not None;contour.append(pt)
            continue
        raise AssertionError('Unsupported mask-Gerber operation: '+line)
    assert contours is None and regions
    return regions

def segment_distance(p,a,b):
    dx,dy=b[0]-a[0],b[1]-a[1];d=dx*dx+dy*dy
    u=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/d)) if d else 0
    return math.hypot(p[0]-(a[0]+u*dx),p[1]-(a[1]+u*dy))
def in_contour(p,contour):
    inside=False
    for a,b in zip(contour,contour[1:]+contour[:1]):
        if segment_distance(p,a,b)<1e-9:return True
        if (a[1]>p[1])!=(b[1]>p[1]):
            crossing=a[0]+(p[1]-a[1])*(b[0]-a[0])/(b[1]-a[1])
            if crossing>p[0]:inside=not inside
    return inside
def evaluate(regions,p):
    inside=any(sum(in_contour(p,c) for c in region)%2 for region in regions)
    distance=min(segment_distance(p,a,b) for r in regions for c in r for a,b in zip(c,c[1:]+c[:1]))
    return {'inside_opening':bool(inside),'nearest_opening_boundary_mm':distance}

def verify(board_path,artwork):
    masks={face:parse_mask(artwork/('stratolink-'+face+'_Mask.'+ext)) for face,ext in [('F','gts'),('B','gbs')]}
    board=pcbnew.LoadBoard(str(board_path));fps={f.GetReference():f for f in board.GetFootprints()}
    pads=[]
    for ref in ['J1','J2']:
        for p in fps[ref].Pads():
            point=(p.GetPosition().x/1e6,p.GetPosition().y/1e6)
            for face,layer in [('F',pcbnew.F_Cu),('B',pcbnew.B_Cu)]:
                if p.IsOnLayer(layer):
                    e=evaluate(masks[face],point);assert e['inside_opening'],('Solar land not exposed in Gerber',ref,p.GetNumber(),face)
                    pads.append({'ref':ref,'pad':p.GetNumber(),'face':face,'center_mm':point,**e})
    thermal=[];u1face='B' if fps['U1'].GetLayer()==pcbnew.B_Cu else 'F'
    for p in fps['U1'].Pads():
        if p.GetNumber()=='21' and p.GetDrillSize().x:
            point=(p.GetPosition().x/1e6,p.GetPosition().y/1e6)
            e=evaluate(masks[u1face],point);assert e['inside_opening'],'U1 EP thermal hole unexpectedly covered'
            thermal.append({'face':u1face,'center_mm':point,**e})
    assert len(thermal)==5
    u6=fps['U6'];under=[]
    if u6.GetValue().startswith('AS7331'):
        assert u6.GetOrientationDegrees()==0,'Update body coordinate transform'
        pos=u6.GetPosition();cx,cy=pos.x/1e6,pos.y/1e6
        for v in board.GetTracks():
            if v.GetClass()!='PCB_VIA':continue
            point=(v.GetPosition().x/1e6,v.GetPosition().y/1e6)
            radius=v.GetDrillValue()/2e6
            annulus_radii={face:v.GetWidth(layer)/2e6 for face,layer in [('F',pcbnew.F_Cu),('B',pcbnew.B_Cu)]}
            # Include every annulus intersecting the maximum 2.7 x 3.75 mm
            # package envelope, even if its center lies outside the body.
            dx=max(abs(point[0]-cx)-1.35,0);dy=max(abs(point[1]-cy)-1.875,0)
            if dx*dx+dy*dy>max(annulus_radii.values())**2:continue
            result={face:evaluate(regions,point) for face,regions in masks.items()}
            for face,e in result.items():
                annulus_radius=annulus_radii[face]
                assert not e['inside_opening'],'Gerber exposes via under U6: '+face
                assert e['nearest_opening_boundary_mm']>annulus_radius,('Gerber exposes via annulus under U6',face,e,annulus_radius)
                e['mask_coverage_beyond_annulus_mm']=e['nearest_opening_boundary_mm']-annulus_radius
            assert v.IsTented(pcbnew.F_Mask) and v.IsTented(pcbnew.B_Mask)
            under.append({'uuid':v.m_Uuid.AsString(),'net':v.GetNetname(),'center_mm':point,'drill_radius_mm':radius,'annulus_radii_mm':annulus_radii,'faces':result,'both_hole_discs_and_annuli_clear_of_mask_openings':True})
    for face,ext in [('F','gto'),('B','gbo')]:
        text=(artwork/('stratolink-'+face+'_Silkscreen.'+ext)).read_text()
        assert not re.search(r'D0[13]\*|G36\*',text),'Drawn silk remains in Gerber'
    return {'pcb_sha256':sha(board_path),'artwork':str(artwork),'mask_files':{face:{'sha256':sha(artwork/('stratolink-'+face+'_Mask.'+ext)),'regions':len(masks[face])} for face,ext in [('F','gts'),('B','gbs')]},
            'solar_pad_window_tests':pads,'U1_thermal_hole_component_side_window_tests':thermal,'under_U6_vias':under,
            'under_U6_selection':'Copper annulus intersects maximum 2.7 x 3.75 mm body envelope',
            'silkscreen_artwork_empty':True,'limitation':'Nominal supplied Gerber geometry only; tent integrity and supplier registration require CAM/manufacturing inspection.'}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--board',type=Path,required=True);p.add_argument('--artwork',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args();app=wx.App(False)
    r=verify(a.board,a.artwork);a.report.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k not in {'solar_pad_window_tests','U1_thermal_hole_component_side_window_tests'}},indent=2))
