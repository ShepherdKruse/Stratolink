#!/usr/bin/env python3
"""Translate C5 only, retaining every native terminal land and all other poses."""
from pathlib import Path
import argparse, hashlib,json,shutil
import pcbnew,wx

def patch_c5(board):
    f=next(f for f in board.GetFootprints()if f.GetReference()=='C5')
    at=[f.GetPosition().x/1e6,f.GetPosition().y/1e6]
    assert at==[64.875,64.707],at
    assert f.GetLayer()==pcbnew.B_Cu and f.GetOrientationDegrees()==180.0
    oldpads={p.GetNumber():{'at':[p.GetPosition().x/1e6,p.GetPosition().y/1e6],'net':p.GetNetname(),'size':[p.GetSize().x/1e6,p.GetSize().y/1e6]}for p in f.Pads()}
    assert len(oldpads)==3 and all(p['size']==[2.5,3.5]for p in oldpads.values())
    f.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(64.875),pcbnew.FromMM(66.007)))
    newpads={p.GetNumber():{'at':[p.GetPosition().x/1e6,p.GetPosition().y/1e6],'net':p.GetNetname(),'size':[p.GetSize().x/1e6,p.GetSize().y/1e6]}for p in f.Pads()}
    ledger=[{'action':'move_footprint','ref':'C5','uuid':f.m_Uuid.AsString(),'before_mm':at,'after_mm':[64.875,66.007],'rotation_deg':180.0,'layer':'B.Cu','pad_before':oldpads,'pad_after':newpads,'reason':'Remove live storage-positive rear land from underneath GNSS RF launch; retain flat case and all three terminal lands. Existing terminal track endpoints remain within translated3.5mm-tall lands, so no signal route changes are required.'}]
    tracks={t.m_Uuid.AsString():t for t in board.GetTracks()}
    for uid,old,new in [('4f4e11d8-24e1-49be-8ad6-88fe1aebc139',[63.5,49.53],[63.5,49.85]),('eb85d24f-882e-4a58-bce7-b5d77ac2077c',[59.69,48.895],[59.6,48.895])]:
        t=tracks[uid];before=[t.GetPosition().x/1e6,t.GetPosition().y/1e6]
        assert before==old and isinstance(t,pcbnew.PCB_VIA) and t.GetNetname()=='GND',(uid,before)
        t.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(new[0]),pcbnew.FromMM(new[1])))
        ledger.append({'action':'move_ground_stitch','uuid':uid,'before_mm':old,'after_mm':new,'diameter_mm':t.GetWidth(pcbnew.F_Cu)/1e6,'drill_mm':t.GetDrillValue()/1e6,'reason':'Clear translated C5 terminal land while retaining the local plated ground connection.'})
    return ledger

def main():
    a=argparse.ArgumentParser();a.add_argument('--source',type=Path,required=True);a.add_argument('--output',type=Path,required=True);args=a.parse_args()
    assert not args.output.exists(),args.output
    sha=hashlib.sha256((args.source/'stratolink.kicad_pcb').read_bytes()).hexdigest()
    shutil.copytree(args.source,args.output)
    p=args.output/'stratolink.kicad_pcb';app=wx.App(False);b=pcbnew.LoadBoard(str(p));ledger=patch_c5(b);b.BuildConnectivity();pcbnew.ZONE_FILLER(b).Fill(b.Zones());pcbnew.SaveBoard(str(p),b)
    (args.output/'c5-ledger.json').write_text(json.dumps({'input_sha256':sha,'output_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'changes':ledger},indent=2)+'\n')
    assert hashlib.sha256((args.source/'stratolink.kicad_pcb').read_bytes()).hexdigest()==sha
if __name__=='__main__':main()
