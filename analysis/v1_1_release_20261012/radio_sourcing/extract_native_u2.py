#!/usr/bin/env python3
"""Read-only canonical U2 pin/RF extraction; run with KiCad Python."""
from pathlib import Path
import datetime, hashlib, json
import wx, pcbnew

root = Path(__file__).resolve().parents[3]
path = root / 'hardware/pcb/stratolink.kicad_pcb'
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
before = digest(path)
app = wx.App(False)
board = pcbnew.LoadBoard(str(path))
board.BuildConnectivity()
fps = {f.GetReference(): f for f in board.GetFootprints()}
u = fps['U2']
pads = sorted(u.Pads(), key=lambda p: int(p.GetNumber()))
rf = next(p for p in pads if p.GetNumber() == '12')
mm = lambda v: [v.x / 1e6, v.y / 1e6]
connected = sorted(x.GetParentFootprint().GetReference() + '.' + x.GetNumber()
                   for x in board.GetConnectivity().GetConnectedItems(rf)
                   if isinstance(x, pcbnew.PAD))
result = {
    'date_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'pcb_sha256': before,
    'footprint': str(u.GetFPID().GetLibItemName()),
    'value': u.GetValue(),
    'position_mm': mm(u.GetPosition()),
    'angle_degrees': u.GetOrientationDegrees(),
    'layer': u.GetLayerName(),
    'pads': [{'number': p.GetNumber(), 'position_mm': mm(p.GetPosition()),
              'local_position_mm': mm(p.GetFPRelativePosition()),
              'size_mm': mm(p.GetSize()), 'net': p.GetNetname(),
              'uuid': p.m_Uuid.AsString()} for p in pads],
    'rf_pad12_net': rf.GetNetname(),
    'rf_connected_pads': connected,
    'rf_track_count': len([t for t in board.GetTracks() if t.GetNetCode() == rf.GetNetCode()]),
    'r4_pads': [{'number': p.GetNumber(), 'position_mm': mm(p.GetPosition()),
                 'size_mm': mm(p.GetSize()), 'net': p.GetNetname()} for p in fps['R4'].Pads()],
}
assert before == digest(path)
assert len(pads) == 32
assert 'AE1.1' in connected and 'D1.2' in connected
(Path(__file__).parent / 'native-u2.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({k: v for k, v in result.items() if k != 'pads'}, indent=2))
