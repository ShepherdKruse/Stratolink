from pathlib import Path
import sys,json,hashlib,pcbnew,wx
project=Path(sys.argv[1]).resolve();out=Path(sys.argv[2]).resolve();app=wx.App(False);path=project/'stratolink.kicad_pcb';b=pcbnew.LoadBoard(str(path));rows=[];n=0

def models(f):
 if f.IsFlipped():f.Flip(f.GetPosition(),False)
 f.SetOrientationDegrees(0)
 return [{'file':m.m_Filename,'offset':[m.m_Offset.x,m.m_Offset.y,m.m_Offset.z],'rotation':[m.m_Rotation.x,m.m_Rotation.y,m.m_Rotation.z],'scale':[m.m_Scale.x,m.m_Scale.y,m.m_Scale.z]}for m in f.Models()]
for f in b.GetFootprints():
 ref=f.GetReference();name=str(f.GetFPID().GetLibItemName());lf=pcbnew.FootprintLoad(str(project/'lib'),name);assert lf is not None;a=models(f);c=models(lf);n+=1
 if a!=c:rows.append({'ref':ref,'library_file':'lib/'+name+'.kicad_mod','board':a,'library':c})
r={'pcb_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'checked_footprints':n,'different':rows};out.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(rows,indent=2))
