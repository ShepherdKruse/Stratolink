#!/usr/bin/env python3
"""Complete a newly built U7 candidate: exact native library and scoped rule."""
from pathlib import Path
import pcbnew, wx, shutil
import build_u7 as u
app = wx.App(False)
b = pcbnew.LoadBoard(str(u.OUT / 'stratolink.kicad_pcb'))
f = next(f for f in b.GetFootprints() if f.GetReference() == 'U7')
pcbnew.FootprintSave(str(u.OUT / 'lib'), f)
shutil.copyfile(Path(__file__).with_name('u7-clearance-rule.kicad_dru'), u.OUT / 'stratolink.kicad_dru')
print('U7 native library and precise clearance rule saved; board unchanged.')
