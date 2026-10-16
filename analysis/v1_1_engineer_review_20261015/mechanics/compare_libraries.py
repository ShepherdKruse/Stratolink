from pathlib import Path
import sys,json,pcbnew,wx,hashlib
project=Path(sys.argv[1]).resolve();output=Path(sys.argv[2]).resolve();app=wx.App(False);b=pcbnew.LoadBoard(str(project/'stratolink.kicad_pcb'));lib=project/'lib'
def xy(q):return[round(q.x/1e6,6),round(q.y/1e6,6)]
def norm(f):
 if f.IsFlipped():f.Flip(f.GetPosition(),False)
 f.SetOrientationDegrees(0);f.SetPosition(pcbnew.VECTOR2I(0,0))
 def pad(p):
  r={'pin':p.GetNumber(),'at':xy(p.GetPosition()),'size':xy(p.GetSize()),'drill':xy(p.GetDrillSize()),'shape':p.GetShape(),'attribute':p.GetAttribute(),'angle':p.GetOrientationDegrees(),'layers':[pcbnew.LayerName(l)for l in p.GetLayerSet().Seq()]}
  for name in ['GetRoundRectRadiusRatio','GetLocalSolderMaskMargin','GetLocalSolderPasteMargin','GetLocalSolderPasteMarginRatio','GetLocalClearance','GetThermalGap','GetThermalSpokeWidth','GetZoneConnection']:
   try:v=getattr(p,name)();r[name]=v if isinstance(v,(int,float,str,bool,type(None)))else str(v)
   except Exception as e:r[name]='API:'+type(e).__name__
  return r
 return sorted([pad(p)for p in f.Pads()],key=lambda x:(x['pin'],x['at']))
report={'pcb_sha256':hashlib.sha256((project/'stratolink.kicad_pcb').read_bytes()).hexdigest(),'loaded':[],'different':[],'missing':[]}
for f in b.GetFootprints():
 ref=f.GetReference();name=str(f.GetFPID().GetLibItemName());l=pcbnew.FootprintLoad(str(lib),name)
 if l is None:report['missing'].append([ref,name]);continue
 report['loaded'].append(ref);a=norm(f);c=norm(l)
 if a!=c:report['different'].append({'ref':ref,'name':name,'board':a,'library':c})
output.write_text(json.dumps(report,indent=2)+'\n');print('loaded',len(report['loaded']),'missing',report['missing'],'different',[x['ref']for x in report['different']])
