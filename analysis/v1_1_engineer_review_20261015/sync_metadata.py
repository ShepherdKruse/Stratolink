#!/usr/bin/env python3
"""Keep edited reusable footprints and schematic placement metadata in sync."""
from pathlib import Path
import argparse, json, sys
import pcbnew, wx
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'analysis/v1_1_release_20261012/as7331/finish'))
from build_green_mask import parse,scalar,prop,one,change_children,set_child

def apply(project):
    board=pcbnew.LoadBoard(str(project/'stratolink.kicad_pcb'))
    refs={f.GetReference():f for f in board.GetFootprints()}
    for ref in ('U4','L2'):
        path=project/'lib'/(str(refs[ref].GetFPID().GetLibItemName())+'.kicad_mod')
        def mask(n,b):
            if n[0]=='pad':
                assert scalar(n,'solder_mask_margin') in ('0.102','0.05')
                return set_child(b,'solder_mask_margin','(solder_mask_margin 0.05)')
            return b
        path.write_text(change_children(path.read_text(),mask))
    path=next((project/'lib').glob('*_C5_*.kicad_mod'))
    counts=[]
    def courtyard(n,b):
        if n[0]!='fp_line' or scalar(n,'layer')!='F.CrtYd':return b
        counts.append(1)
        for key in ('start','end'):
            x,y=map(float,one(n,key));assert abs(x)==7.375 and y in (-20.375,15.375)
            x=8 if x>0 else -8;y=-21.25 if y<0 else 16
            b=set_child(b,key,f'({key} {x} {y})')
        return b
    path.write_text(change_children(path.read_text(),courtyard));assert len(counts)==4
    path=project/'stratolink.kicad_sch';changed=[]
    def symbol(n,b):
        if n[0]=='symbol' and prop(n,'Reference') in ('J1','J2','J20'):
            assert scalar(n,'in_pos_files')=='yes'
            changed.append(prop(n,'Reference'))
            return set_child(b,'in_pos_files','(in_pos_files no)')
        return b
    path.write_text(change_children(path.read_text(),symbol));assert len(changed)==3
    # Keep the exposed ground minus fully within the connected pour.
    path=project/'stratolink.kicad_pcb';b=pcbnew.LoadBoard(str(path))
    for d in b.GetDrawings():
        if d.m_Uuid.AsString()=='517aa68d-ce15-590c-89c7-5c81211a9ef5':d.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(74.3),pcbnew.FromMM(55)))
    pcbnew.SaveBoard(str(path),b)
    (project/'metadata-ledger.json').write_text(json.dumps({'library_mask_updates':['U4','L2'],'library_courtyard_update':'C5, match incoming larger envelope','schematic_excluded_from_position':changed,'right_minus_final_mm':[74.3,55]},indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--project',type=Path,required=True);a=p.parse_args();app=wx.App(False);apply(a.project)
