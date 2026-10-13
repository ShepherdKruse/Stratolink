#!/usr/bin/env python3
"""Read-only ground-zone sample near existing GNSS feed.

A differential 50 µm grid screen, not an impedance or RF field solver. Samples
only filled back-ground zones; ground pads/tracks may additionally carry return.
"""
from pathlib import Path
import argparse,base64,hashlib,json
import pcbnew,wx

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--pcb',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--refilled-pcb',type=Path,required=True);a=ap.parse_args()
    before=hashlib.sha256(a.pcb.read_bytes()).hexdigest();fill=json.loads((a.refilled_pcb.parent/'manifest.json').read_text());assert fill['source_hashes']['stratolink.kicad_pcb']==before;assert hashlib.sha256(a.refilled_pcb.read_bytes()).hexdigest()==fill['refilled_pcb_sha256'];app=wx.App(False);b=pcbnew.LoadBoard(str(a.refilled_pcb))
    polys=[z.GetFilledPolysList(pcbnew.B_Cu) for z in b.Zones() if z.GetNetname()=='GND' and not z.GetIsRuleArea() and z.IsOnLayer(pcbnew.B_Cu)]
    xmin,ymin,step,nx,ny=59.,33.,.05,100,260
    samples=bytearray(any(p.Contains(pcbnew.VECTOR2I(round((xmin+(ix+.5)*step)*1e6),round((ymin+(iy+.5)*step)*1e6))) for p in polys) for iy in range(ny) for ix in range(nx))
    centerline=[]
    for iy in range(206):
        x,y=62.882,33.218+iy*.05
        centerline.append([x,round(y,6),any(p.Contains(pcbnew.VECTOR2I(round(x*1e6),round(y*1e6))) for p in polys)])
    result=dict(pcb=str(a.pcb),pcb_sha256=before,project_aware_refill_sha256=fill['refilled_pcb_sha256'],description='B.Cu filled GND zone only; saved native CLI project-aware refill; differential sample, not RF or impedance validation',grid=dict(xmin=xmin,ymin=ymin,step=step,nx=nx,ny=ny),covered_samples=sum(samples),samples_base64=base64.b64encode(samples).decode(),vertical_feed_centerline=centerline)
    assert hashlib.sha256(a.pcb.read_bytes()).hexdigest()==before
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['samples_base64','vertical_feed_centerline']},indent=2))
if __name__=='__main__':main()
