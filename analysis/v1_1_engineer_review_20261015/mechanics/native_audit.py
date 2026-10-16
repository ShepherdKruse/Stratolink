from pathlib import Path
import sys,json,hashlib,os,pcbnew,wx
project=Path(sys.argv[1]).resolve(); output=Path(sys.argv[2]).resolve()
app=wx.App(False)
def xy(x):return [x.x/1e6,x.y/1e6]
def inspect(p):
 raw=p.read_bytes();b=pcbnew.LoadBoard(str(p));d={'source':str(p),'sha256':hashlib.sha256(raw).hexdigest(),'footprints':{},'silk':[],'holes':[],'models':[],'thickness_mm':b.GetDesignSettings().GetBoardThickness()/1e6}
 for f in b.GetFootprints():
  ref=f.GetReference();row={'at':xy(f.GetPosition()),'angle':f.GetOrientationDegrees(),'layer':f.GetLayerName(),'fpid':str(f.GetFPID().GetLibNickname())+':'+str(f.GetFPID().GetLibItemName()),'value':f.GetValue(),'attributes':f.GetAttributes(),'pads':[],'models':[],'fields':{q.GetName():q.GetText() for q in f.GetFields()}}
  for q in f.Pads():
   layers=[b.GetLayerName(l)for l in q.GetLayerSet().Seq()];z={'pin':q.GetNumber(),'at':xy(q.GetPosition()),'local':xy(q.GetFPRelativePosition()),'size':xy(q.GetSize()),'drill':xy(q.GetDrillSize()),'shape':q.GetShape(),'layers':layers,'net':q.GetNetname(),'orientation':q.GetOrientationDegrees(),'attr':q.GetAttribute()}
   row['pads'].append(z)
   if max(z['drill'])>0:d['holes'].append({'ref':ref,**z,'nominal_min_annulus_mm':min([(a-b)/2 for a,b in zip(z['size'],z['drill'])])})
  for m in f.Models():
   path=m.m_Filename.replace('${KIPRJMOD}',str(project));path=path.replace('${KICAD9_3DMODEL_DIR}','/Applications/KiCad/KiCad.app/Contents/SharedSupport/3dmodels').replace('${KICAD10_3DMODEL_DIR}','/Applications/KiCad/KiCad.app/Contents/SharedSupport/3dmodels')
   z={'ref':ref,'file':m.m_Filename,'offset':[m.m_Offset.x,m.m_Offset.y,m.m_Offset.z],'rotation':[m.m_Rotation.x,m.m_Rotation.y,m.m_Rotation.z],'scale':[m.m_Scale.x,m.m_Scale.y,m.m_Scale.z],'resolved':path,'exists':Path(path).is_file(),'sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest() if Path(path).is_file() else None}
   row['models'].append(z);d['models'].append(z)
  for g in list(f.GraphicalItems())+list(f.GetFields()):
   if g.GetLayer()in[pcbnew.F_SilkS,pcbnew.B_SilkS]:d['silk'].append({'ref':ref,'type':g.GetClass(),'layer':g.GetLayerName(),'text':g.GetText()if hasattr(g,'GetText')else None,'visible':g.IsVisible()if hasattr(g,'IsVisible')else True})
  d['footprints'][ref]=row
 for g in b.GetDrawings():
  if g.GetLayer()in[pcbnew.F_SilkS,pcbnew.B_SilkS]:d['silk'].append({'ref':None,'type':g.GetClass(),'layer':g.GetLayerName(),'text':g.GetText()if hasattr(g,'GetText')else None})
 for t in b.GetTracks():
  if isinstance(t,pcbnew.PCB_VIA):d['holes'].append({'ref':'via','at':xy(t.GetPosition()),'drill':[t.GetDrill()/1e6]*2,'size':[t.GetWidth(pcbnew.F_Cu)/1e6]*2,'nominal_min_annulus_mm':(t.GetWidth(pcbnew.F_Cu)-t.GetDrill())/2e6})
 assert p.read_bytes()==raw
 return d
d=inspect(project/'stratolink.kicad_pcb');output.write_text(json.dumps(d,indent=2)+'\n');print(d['sha256'],len(d['footprints']),len(d['models']))
