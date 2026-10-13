#!/usr/bin/env python3
"""Native copper-box proximity screen for REXT.

Reports conservative planar lower bounds, not a parasitic or noise simulation.
Actual copper can be farther apart than its bounding rectangles. Opposite-layer
measurements are projected distances, not through-substrate 3-D clearances.
"""
import argparse,hashlib,json,math
from pathlib import Path
import pcbnew,wx
HERE=Path(__file__).resolve().parent

def box(o):
    b=o.GetBoundingBox();return [b.GetLeft()/1e6,b.GetTop()/1e6,b.GetRight()/1e6,b.GetBottom()/1e6]
def sep(a,b):return math.hypot(max(a[0]-b[2],b[0]-a[2],0),max(a[1]-b[3],b[1]-a[3],0))
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--pcb',type=Path,required=True);args=ap.parse_args()
    app=wx.App(False);b=pcbnew.LoadBoard(str(args.pcb));objects=[]
    for f in b.GetFootprints():
        for p in f.Pads():objects.append((p,f.GetReference()+'.'+p.GetNumber()))
    for t in b.GetTracks():objects.append((t,t.m_Uuid.AsString()))
    records=[dict(identifier=i,net=o.GetNetname(),kind=o.GetClass(),bounds_mm=box(o),layers=[pcbnew.LayerName(l) for l in [pcbnew.F_Cu,pcbnew.B_Cu] if o.IsOnLayer(l)]) for o,i in objects]
    refs=[r for r in records if r['net']=='/UV_REXT'];assert refs
    categories={
      'same_layer_I2C':lambda r:'F.Cu' in r['layers'] and ('SDA' in r['net'] or 'SCL' in r['net']),
      'opposite_layer_I2C_projected':lambda r:'B.Cu' in r['layers'] and ('SDA' in r['net'] or 'SCL' in r['net']),
      'opposite_layer_switching_projected':lambda r:'B.Cu' in r['layers'] and ('LBOOST' in r['net'] or 'LBUCK' in r['net']),
      'same_layer_PB5':lambda r:'F.Cu' in r['layers'] and r['net']=='PB5',
      'opposite_layer_PB5_projected':lambda r:'B.Cu' in r['layers'] and r['net']=='PB5',
      'same_layer_VSTOR':lambda r:'F.Cu' in r['layers'] and r['net']=='VSTOR',
      'opposite_layer_VSTOR_projected':lambda r:'B.Cu' in r['layers'] and r['net']=='VSTOR',
      'any_layer_GNSS_feed_projected':lambda r:r['net']=='Net-(AE2-A)',
      'opposite_layer_balancer_projected':lambda r:'B.Cu' in r['layers'] and r['net'].startswith('/SC_'),
    }
    near={}
    for name,predicate in categories.items():
        pairs=[(sep(a['bounds_mm'],c['bounds_mm']),a,c) for a in refs for c in records if predicate(c)]
        distance,a,c=min(pairs,key=lambda t:t[0]);near[name]=dict(lower_bound_mm=distance,rext_item=a,nearest_other_item=c)
    trace_lengths=[]
    for o,i in objects:
        if o.GetNetname()=='/UV_REXT' and isinstance(o,pcbnew.PCB_TRACK):trace_lengths.append(dict(identifier=i,length_mm=o.GetLength()/1e6,layer=o.GetLayerName()))
    assert trace_lengths,'REXT routing incomplete; no reference trace to review'
    r=dict(pcb=str(args.pcb),pcb_sha256=hashlib.sha256(args.pcb.read_bytes()).hexdigest(),method=__doc__,reference_copper=refs,reference_track_lengths=trace_lengths,total_reference_track_mm=sum(t['length_mm'] for t in trace_lengths),nearest=near)
    (HERE/'analog-screen.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'rext_track_mm':r['total_reference_track_mm'],'distances':{k:v['lower_bound_mm'] for k,v in near.items()}},indent=2))
if __name__=='__main__':main()
