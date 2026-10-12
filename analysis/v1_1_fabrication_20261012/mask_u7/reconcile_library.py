#!/usr/bin/env python3
"""Export only the corrected placed U7 footprint to its scratch reusable library."""
from pathlib import Path
import hashlib,pcbnew,wx
p=Path.home()/'Repositories/ai-working/scratch/stratolink-u7-mask/candidate'
source=(p/'stratolink.kicad_pcb').read_bytes();app=wx.App(False);b=pcbnew.LoadBoard(str(p/'stratolink.kicad_pcb'));f=next(f for f in b.GetFootprints() if f.GetReference()=='U7')
f.SetPosition(pcbnew.VECTOR2I(0,0));f.SetOrientationDegrees(0);f.SetReference('REF**')
assert all(pad.GetSolderMaskExpansion(pcbnew.F_Mask)==0 for pad in f.Pads())
pcbnew.FootprintSave(str(p/'lib'),f)
assert (p/'stratolink.kicad_pcb').read_bytes()==source
print(hashlib.sha256((p/'lib/PQFN50P200X200100-12N.kicad_mod').read_bytes()).hexdigest())
