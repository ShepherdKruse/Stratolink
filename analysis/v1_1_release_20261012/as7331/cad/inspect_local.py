from pathlib import Path
import json,pcbnew
b=pcbnew.LoadBoard('/Users/twarn/Repositories/Stratolink/hardware/pcb/stratolink.kicad_pcb')
def pt(p):return [pcbnew.ToMM(p.x),pcbnew.ToMM(p.y)]
r={'footprints':[],'tracks':[]}
for f in b.GetFootprints():
 x,y=pt(f.GetPosition())
 if 64<x<76 and 34<y<48:r['footprints'].append(dict(ref=f.GetReference(),position=[x,y],angle=f.GetOrientationDegrees(),side=f.GetLayerName(),pads=[dict(n=p.GetNumber(),at=pt(p.GetPosition()),size=pt(p.GetSize()),net=p.GetNetname()) for p in f.Pads()]))
for t in b.GetTracks():
 s,e=pt(t.GetStart()),pt(t.GetEnd())
 if min(s[0],e[0])<76 and max(s[0],e[0])>64 and min(s[1],e[1])<48 and max(s[1],e[1])>34:r['tracks'].append(dict(uuid=t.m_Uuid.AsString(),start=s,end=e,net=t.GetNetname(),layer=t.GetLayerName(),width=pcbnew.ToMM(t.GetWidth()),type=t.GetClass()))
Path('analysis/v1_1_release_20261012/as7331/cad/baseline-local.json').write_text(json.dumps(r,indent=2))
print(json.dumps(r['footprints'],indent=2))
