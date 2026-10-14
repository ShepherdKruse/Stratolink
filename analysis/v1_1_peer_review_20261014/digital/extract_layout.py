#!/usr/bin/env python3
"""Read-only native board digital-net geometry extraction; lengths are centerlines."""
from pathlib import Path
import json,hashlib,math,heapq,subprocess
import pcbnew,wx
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
SELECT={'SCL','SDA','Net-(U3-SCL)','Net-(U3-SDA)','TX','RX','Net-(U3-TXD)','Net-(U3-RXD)','SWCLK','SWDIO','RST','BOOT0','PA1','PA9','PB2'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def xy(p):return [p.x/1e6,p.y/1e6]
def extract(path):
 b=pcbnew.LoadBoard(str(path));nets={}
 for n in b.GetNetsByNetcode().values():
  name=n.GetNetname()
  if name not in SELECT:continue
  tracks=[];vias=[];pads=[]
  for t in b.GetTracks():
   if t.GetNetname()!=name:continue
   if t.GetClass()=='PCB_VIA':
    vias.append({'uuid':t.m_Uuid.AsString(),'position_mm':xy(t.GetPosition()),'diameter_mm':t.GetWidth(pcbnew.F_Cu)/1e6,'drill_mm':t.GetDrillValue()/1e6});continue
   assert t.GetClass()=='PCB_TRACK','Arc unsupported'
   tracks.append({'uuid':t.m_Uuid.AsString(),'start_mm':xy(t.GetStart()),'end_mm':xy(t.GetEnd()),'layer':pcbnew.LayerName(t.GetLayer()),'width_mm':t.GetWidth()/1e6,'length_mm':t.GetLength()/1e6})
  for f in b.GetFootprints():
   for p in f.Pads():
    if p.GetNetname()==name:pads.append({'ref':f.GetReference(),'value':f.GetValue(),'number':p.GetNumber(),'position_mm':xy(p.GetPosition()),'size_mm':xy(p.GetSize()),'layers':[pcbnew.LayerName(l) for l in [pcbnew.F_Cu,pcbnew.B_Cu] if p.IsOnLayer(l)]})
  nets[name]={'tracks':tracks,'vias':vias,'pads':pads,'total_track_mm':sum(t['length_mm'] for t in tracks),'by_layer_mm':{l:sum(t['length_mm'] for t in tracks if t['layer']==l) for l in ['F.Cu','B.Cu']}}
 mapping={}
 for f in b.GetFootprints():
  if f.GetReference() in ['U2','U3','J3','J4','J20','R9','R10','R11','R12','R13','R14','R15','R16']:
   mapping[f.GetReference()]={'value':f.GetValue(),'pads':{p.GetNumber():p.GetNetname() for p in f.Pads()}}
 return {'path':str(path),'sha256':sha(path),'nets':nets,'part_pin_nets':mapping}
if __name__=='__main__':
 app=wx.App(False);current=extract(ROOT/'hardware/pcb/stratolink.kicad_pcb');old=extract(HERE/'flown-v1.kicad_pcb')
 (HERE/'layout.json').write_text(json.dumps({'current':current,'flown_v1':old},indent=2)+'\n')
 for name,n in current['nets'].items():print(name,round(n['total_track_mm'],3),'mm',len(n['vias']),'vias',[(p['ref'],p['number']) for p in n['pads']])
 print('Pin net changes:',json.dumps({r:{'before':old['part_pin_nets'].get(r),'after':v} for r,v in current['part_pin_nets'].items() if old['part_pin_nets'].get(r,{}).get('pads')!=v['pads']},indent=2))
