#!/usr/bin/env python3
"""Read actual native Cu/paste Gerber flashes, independently of source margin metadata."""
from pathlib import Path
import argparse,hashlib,json,math,re,shutil,subprocess
CLI='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'

def flashdata(path):
    text=path.read_text();apertures={}
    for code,macro,param in re.findall(r'%ADD(\d+)([A-Za-z]+),([^*]+)\*%',text):
        if macro!='RoundRect':continue
        values=list(map(float,param.split('X')));r=values[0];xs=values[1:9:2];ys=values[2:9:2]
        w=max(xs)-min(xs)+2*r;h=max(ys)-min(ys)+2*r
        area=w*h-(4-math.pi)*r*r;perimeter=2*(w+h)-8*r+2*math.pi*r
        apertures[code]=dict(width_mm=w,height_mm=h,round_radius_mm=r,area_mm2=area,perimeter_mm=perimeter)
    result=[];code=comp=pin=None
    for line in text.splitlines():
        m=re.fullmatch(r'D(\d+)\*',line)
        if m:code=m[1]
        m=re.fullmatch(r'%TO.C,([^*]+)\*%',line)
        if m:comp=m[1];pin=None
        m=re.match(r'%TO.P,([^,]+),([^,*]+)',line)
        if m:comp,pin=m.groups()
        if line=='%TD*%':comp=pin=None
        m=re.fullmatch(r'X(-?\d+)Y(-?\d+)D03\*',line)
        if m and comp=='U7':
            assert code in apertures,'Unexpected U7 aperture macro'
            result.append(dict(pin=pin,center_mm=[int(m[1])/1e6,int(m[2])/1e6],aperture_code=code,**apertures[code]))
    assert len(result)==12
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False);source=args.candidate/'stratolink.kicad_pcb';copied=args.output/'stratolink.kicad_pcb';shutil.copyfile(source,copied)
    digest=hashlib.sha256(copied.read_bytes()).hexdigest()
    r=subprocess.run([CLI,'pcb','export','gerbers','--layers','F.Cu,F.Paste','--output',str(args.output),str(copied)],capture_output=True,text=True,check=True);(args.output/'export.log').write_text(r.stdout+r.stderr)
    cu=flashdata(args.output/'stratolink-F_Cu.gtl');paste=flashdata(args.output/'stratolink-F_Paste.gtp');rows=[]
    for c in cu:
        pp=next(p for p in paste if p['center_mm']==c['center_mm']);ratio=pp['area_mm2']/c['area_mm2']
        assert abs(ratio-.81)<1e-10 and abs(pp['round_radius_mm']/c['round_radius_mm']-.9)<1e-10
        rows.append(dict(pin=c['pin'],copper=c,paste=pp,paste_to_copper_area=ratio,
            aperture_area_ratio_at_stencil_mm={str(t):pp['area_mm2']/(pp['perimeter_mm']*t) for t in [.08,.10,.12,.15]}))
    output=dict(source=str(source),snapshot_pcb_sha256=digest,method='KiCad native Gerber RoundRect aperture macros and U7-tagged flash centers, exact analytical round-rectangle area and perimeter',
        twelve_paste_apertures_match_twelve_copper_pads=True,linear_ratio=.9,area_ratio=.81,pads=rows,
        process_limit='These area ratios are geometric screening only; stencil thickness/reduction and bare-board printing require supplier process review. No global reduction was applied.')
    (args.output/'u7-paste-proof.json').write_text(json.dumps(output,indent=2)+'\n');print(json.dumps({'output':str(args.output),'snapshot':digest,'pads':12,'ratio':.81,'area_mm2':rows[0]['paste']['area_mm2'],'area_ratio_0.1mm':rows[0]['aperture_area_ratio_at_stencil_mm']['0.1']},indent=2))
if __name__=='__main__':main()
