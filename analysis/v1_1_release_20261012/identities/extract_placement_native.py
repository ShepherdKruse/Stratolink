import pcbnew,wx,json
from pathlib import Path
app=wx.App(False);b=pcbnew.LoadBoard('hardware/pcb/stratolink.kicad_pcb');out={}
for f in b.GetFootprints():
 if f.GetReference() not in ['U1','U2','U3','U4','U5','U6','U7','U8']:continue
 models=[]
 for m in f.Models():models.append(dict(filename=m.m_Filename,offset=[getattr(m.m_Offset,k) for k in 'xyz'],rotation=[getattr(m.m_Rotation,k) for k in 'xyz']))
 out[f.GetReference()]={'at':[f.GetPosition().x/1e6,f.GetPosition().y/1e6],'rotation':f.GetOrientationDegrees(),'layer':f.GetLayerName(),'fp':str(f.GetFPID().GetLibItemName()),'models':models,'pads':[{'n':p.GetNumber(),'xy':[p.GetPosition().x/1e6,p.GetPosition().y/1e6],'local':[p.GetFPRelativePosition().x/1e6,p.GetFPRelativePosition().y/1e6],'size':[p.GetSize().x/1e6,p.GetSize().y/1e6],'net':p.GetNetname()} for p in f.Pads()]}
p=Path('/Users/twarn/Repositories/ai-working/scratch/stratolink-release-20261012/identities/placement-review');p.mkdir(exist_ok=True);(p/'native.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
