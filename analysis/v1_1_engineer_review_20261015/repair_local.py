#!/usr/bin/env python3
"""Second local repair pass: ground continuity and mask clearances."""
import argparse, hashlib, json
from pathlib import Path
import pcbnew, wx
from repair import vec, xy

def apply(b):
    ledger=[]
    refs={f.GetReference():f for f in b.GetFootprints()}
    items={t.m_Uuid.AsString():t for t in b.GetTracks()}
    for ref in ('U4','L2'):
        for p in refs[ref].Pads():
            p.SetLocalSolderMaskMargin(pcbnew.FromMM(.05))
        ledger.append(dict(ref=ref,action='pad_mask_expansion_0p05',reason='Preserve copper routing; retain >=0.09 mm mask-to-foreign-copper gap'))
    # Join the already connected converter ground group to the main ground plane.
    v=pcbnew.PCB_VIA(b);v.SetPosition(vec(64.25,32.20));v.SetWidth(pcbnew.FromMM(.6));v.SetDrill(pcbnew.FromMM(.3));v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetNet(b.FindNet('GND'));b.Add(v)
    ledger.append(dict(uuid=v.m_Uuid.AsString(),action='add_ground_stitch',at=[64.25,32.20],reason='Connect U1/C6/C20 ground group to main ground'))
    for z in b.Zones():
        if z.m_Uuid.AsString() in ['f954dff9-4ad5-4f1c-b210-537ad56aea41','09c941a2-a889-457b-ae85-cdf2c8c21c0d']:
            z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
            ledger.append(dict(uuid=z.m_Uuid.AsString(),action='remove_unconnected_fill_islands'))
    for d in b.GetDrawings():
        if d.m_Uuid.AsString()=='517aa68d-ce15-590c-89c7-5c81211a9ef5':
            d.SetPosition(vec(74.2,54.5));ledger.append(dict(uuid=d.m_Uuid.AsString(),action='move_right_minus_mask',before=[73,54.5],after=[74.2,54.5],reason='Keep solder mask opening away from GNSS TXD'))
    return ledger

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--project',type=Path,required=True);a=p.parse_args();app=wx.App(False)
    path=a.project/'stratolink.kicad_pcb';before=hashlib.sha256(path.read_bytes()).hexdigest();b=pcbnew.LoadBoard(str(path));ledger=apply(b);pcbnew.SaveBoard(str(path),b)
    (a.project/'repair-local-ledger.json').write_text(json.dumps(dict(input_sha256=before,output_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),changes=ledger),indent=2)+'\n')
