from pathlib import Path
import sys,pcbnew,wx
app=wx.App(False);p=Path(sys.argv[1]);b=pcbnew.LoadBoard(str(p/'stratolink.kicad_pcb'));by={f.GetReference():f for f in b.GetFootprints()}
for ref in ['C14','C16','C23','R27']:
 f=pcbnew.Cast_to_FOOTPRINT(by[ref].Duplicate(False));f.SetPosition(pcbnew.VECTOR2I(0,0));f.SetOrientationDegrees(0);f.ClearAllNets();pcbnew.FootprintSave(str(p/'lib'),f)
