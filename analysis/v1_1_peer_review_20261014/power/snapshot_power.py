#!/usr/bin/env python3
"""Read native KiCad power geometry without altering the board."""
from pathlib import Path
import hashlib,json,math
import pcbnew,wx

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
source=ROOT/'hardware/pcb/stratolink.kicad_pcb'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def mm(p): return [pcbnew.ToMM(p.x),pcbnew.ToMM(p.y)]
before=sha(source)
app=wx.App(False)
b=pcbnew.LoadBoard(str(source))
fps={}
for f in b.GetFootprints():
    ref=f.GetReference()
    fps[ref]={'at_mm':mm(f.GetPosition()),'value':f.GetValue(),'layer':f.GetLayerName(),'angle_deg':f.GetOrientationDegrees(),'footprint':str(f.GetFPID().GetLibNickname())+':'+str(f.GetFPID().GetLibItemName()),'pads':{p.GetNumber():{'at_mm':mm(p.GetPosition()),'net':p.GetNetname(),'size_mm':mm(p.GetSize())} for p in f.Pads()}}
tracks=[]
for t in b.GetTracks():
    if t.GetNetname() in ['Net-(U1-LBOOST)','Net-(U1-LBUCK)','+3.3V','VSTOR','Net-(U3-VCC)','Net-(AE2-A)']:
        tracks.append({'uuid':t.m_Uuid.AsString(),'net':t.GetNetname(),'start_mm':mm(t.GetStart()),'end_mm':mm(t.GetEnd()),'layer':t.GetLayerName(),'width_mm':pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu) if isinstance(t,pcbnew.PCB_VIA) else t.GetWidth()),'class':t.GetClass()})
result={'source':str(source.relative_to(ROOT)),'sha256':before,'schematic_sha256':sha(ROOT/'hardware/pcb/stratolink.kicad_sch'),'footprints':fps,'tracks':tracks}
assert before==sha(source)
(HERE/'native-power.json').write_text(json.dumps(result,indent=2)+'\n')
for ref in ['U1','L1','L2','C2','C3','C4','C6','C7','C8','C21','C10','C11','FB1','U2','U3']:
    print(ref,json.dumps(fps[ref]))
