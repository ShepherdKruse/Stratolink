#!/usr/bin/env python3
"""Read native zone rules and pad connection overrides without refilling/saving."""
from pathlib import Path
import argparse,hashlib,json,sys
import pcbnew,wx
p=argparse.ArgumentParser(description=__doc__)
for n in ['repo','pcb','output']:p.add_argument('--'+n,type=Path,required=True)
a=p.parse_args();assert not a.output.exists(),a.output
sys.path.insert(0,str(a.repo/'analysis/v1_1_solar_attachments_20261012/materials'));from extract_native import contours
raw=a.pcb.read_bytes();app=wx.App(False);b=pcbnew.LoadBoard(str(a.pcb));pads=[];zones=[]
for f in b.GetFootprints():
 for p in f.Pads():
  if p.GetNetname()=='GND':pads.append({'ref':f.GetReference(),'pin':p.GetNumber(),'uuid':p.m_Uuid.AsString(),'local_zone_connection':p.GetLocalZoneConnection(),'resolved_pad_footprint_override':p.GetZoneConnectionOverrides()})
for z in b.Zones():
 if z.GetNetname()=='GND':zones.append({'uuid':z.m_Uuid.AsString(),'priority':z.GetAssignedPriority(),'pad_connection':z.GetPadConnection(),'thermal_gap_mm':z.GetThermalReliefGap()/1e6,'thermal_spoke_width_mm':z.GetThermalReliefSpokeWidth()/1e6,'layers':[b.GetLayerName(l)for l in [pcbnew.F_Cu,pcbnew.B_Cu]if z.IsOnLayer(l)],'outline':contours(z.Outline())})
assert a.pcb.read_bytes()==raw
a.output.write_text(json.dumps({'pcb_sha256':hashlib.sha256(raw).hexdigest(),'ground_pads':pads,'ground_zones':zones,'source_bytes_unchanged':True},indent=2)+'\n')
