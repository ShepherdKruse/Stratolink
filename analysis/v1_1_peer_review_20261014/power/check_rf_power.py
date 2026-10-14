#!/usr/bin/env python3
"""Read-only final RF-candidate power/layout invariant review with native KiCad."""
from pathlib import Path
import sys,json,hashlib,argparse
import pcbnew,wx
H=Path(__file__).resolve().parent;ROOT=H.parents[2]
sys.path.insert(0,str(ROOT/'analysis/v1_1_solar_attachments_20261012/materials'))
from extract_native import contours
ap=argparse.ArgumentParser();ap.add_argument('--pcb',type=Path,required=True);ap.add_argument('--name',default='rf-final-power');args=ap.parse_args()
app=wx.App(False)
base=Path('/Users/twarn/Repositories/ai-working/scratch/stratolink-peer-review-20261014/fabrication/copper-final4/stratolink.kicad_pcb')
def xy(q):return [q.x/1e6,q.y/1e6]
def read(p):
 raw=p.read_bytes();b=pcbnew.LoadBoard(str(p));f={x.GetReference():x for x in b.GetFootprints()};result={'source':str(p),'sha256':hashlib.sha256(raw).hexdigest(),'critical_placements':{},'balance_pins':{},'switch_tracks':[],'C5':{},'rear_pads':[]}
 for ref in ['U1','L1','L2','C2','C3','C4','C6','U8','R24','R25','R26','C22']:
  x=f[ref];result['critical_placements'][ref]={'at':xy(x.GetPosition()),'angle':x.GetOrientationDegrees(),'side':x.GetLayerName(),'pads':{p.GetNumber():{'at':xy(p.GetPosition()),'net':p.GetNetname(),'size':xy(p.GetSize())} for p in x.Pads()}}
 for ref in ['U8','R24','R25','R26','C22','C5']:
  result['balance_pins'][ref]={p.GetNumber():p.GetNetname() for p in f[ref].Pads()}
 for t in b.GetTracks():
  if t.GetNetname() not in ['Net-(U1-LBOOST)','Net-(U1-LBUCK)']:continue
  row={'uuid':t.m_Uuid.AsString(),'kind':t.GetClass(),'net':t.GetNetname(),'layer':t.GetLayerName(),'start':xy(t.GetStart()),'end':xy(t.GetEnd()),'width':t.GetWidth()/1e6}
  if isinstance(t,pcbnew.PCB_ARC):row['mid']=xy(t.GetMid())
  result['switch_tracks'].append(row)
 result['switch_tracks']=sorted(result['switch_tracks'],key=lambda x:x['uuid'])
 c=f['C5'];result['C5']={'at':xy(c.GetPosition()),'angle':c.GetOrientationDegrees(),'side':c.GetLayerName(),'pads':{p.GetNumber():{'at':xy(p.GetPosition()),'net':p.GetNetname(),'size':xy(p.GetSize())} for p in c.Pads()}}
 for ref,x in f.items():
  if ref=='C5':continue
  for p0 in x.Pads():
   if p0.IsOnLayer(pcbnew.B_Cu):
    poly=pcbnew.SHAPE_POLY_SET();p0.TransformShapeToPolygon(poly,pcbnew.B_Cu,0,1000,pcbnew.ERROR_OUTSIDE);result['rear_pads'].append({'ref':ref,'pin':p0.GetNumber(),'net':p0.GetNetname(),'polygons':contours(poly)})
 outline=pcbnew.SHAPE_POLY_SET();assert b.GetBoardPolygonOutlines(outline,False,None,False,False);result['outline']=contours(outline)
 assert p.read_bytes()==raw
 return result
before=read(base);after=read(args.pcb.resolve())
checks={'critical_power_and_balance_placements_exact':before['critical_placements']==after['critical_placements'],'balance_pin_nets_exact':before['balance_pins']==after['balance_pins'],'LBOOST_LBUCK_tracks_exact':before['switch_tracks']==after['switch_tracks'],'C5_retains_back_180deg':after['C5']['side']=='B.Cu' and abs(after['C5']['angle']-180)<1e-6,'C5_pad_sizes_and_nets_exact':all(v['net']==after['C5']['pads'][k]['net'] and v['size']==after['C5']['pads'][k]['size'] for k,v in before['C5']['pads'].items())}
translation=[after['C5']['at'][i]-before['C5']['at'][i] for i in range(2)]
checks['C5_pad_translation_is_rigid']=all(all(abs(after['C5']['pads'][k]['at'][i]-v['at'][i]-translation[i])<1e-6 for i in range(2)) for k,v in before['C5']['pads'].items())
out={'status':'PASS' if all(checks.values()) else 'REVIEW','checks':checks,'C5_translation_mm':translation,'baseline':before,'candidate':after}
(H/(args.name+'.json')).write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({'status':out['status'],'checks':checks,'C5_translation_mm':translation,'candidate_sha256':after['sha256']},indent=2))
