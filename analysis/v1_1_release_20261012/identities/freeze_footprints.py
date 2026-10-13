#!/usr/bin/env python3
"""Export immutable board-specific release library copies via KiCad's own serializer."""
from pathlib import Path
import pcbnew,wx,json
HERE=Path(__file__).resolve().parent
r=json.loads((HERE/'metadata-build.json').read_text());out=Path(r['candidate']);app=wx.App(False);b=pcbnew.LoadBoard(str(out/'stratolink.kicad_pcb'))
for fp in b.GetFootprints():
 ref=fp.GetReference()
 if ref not in r['new_footprints']:continue
 name=r['new_footprints'][ref]
 # Native FootprintSave normalizes pads/graphics but leaves embedded rule-area outlines in global coordinates.
 # Move the in-memory footprint before export; never save this transformed board.
 if ref in {'U3','U4','J20'}:
  fp.SetPosition(pcbnew.VECTOR2I(0,0));fp.SetOrientationDegrees(0)
 pcbnew.FootprintSave(str(out/'lib'),fp)
 assert (out/'lib'/(name+'.kicad_mod')).exists(),name
print('Saved',len(r['new_footprints']),'native library footprints')
