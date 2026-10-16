#!/usr/bin/env python3
"""Apply individually reviewed local corrections to the engineer's reroute.

Run with KiCad's Python against a disposable complete project directory.
Input ZIP and intake files are never modified. Native DRC/refill follows.
"""
import argparse
import hashlib
import json
from pathlib import Path
import pcbnew
import wx

def xy(v):
    return [v.x / 1e6, v.y / 1e6]

def vec(x, y):
    return pcbnew.VECTOR2I(round(x * 1e6), round(y * 1e6))

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project', required=True, type=Path)
    p.add_argument('--baseline', required=True, type=Path)
    a = p.parse_args()
    app = wx.App(False)
    path = a.project / 'stratolink.kicad_pcb'
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    b = pcbnew.LoadBoard(str(path))
    baseline = pcbnew.LoadBoard(str(a.baseline))
    items = {t.m_Uuid.AsString(): t for t in b.GetTracks()}
    ledger = []
    for uid, old, new, reason in [
        ('1d57c0b4-a7e4-49d1-a01f-ff4858a853ef', [62.23,69.215], [62.25,69.75], 'Clear PA1 short'),
        ('fc05659b-7975-428e-9843-c981acda714c', [62.23,67.945], [62.25,67.55], 'Clear PA9 short'),
        ('93406d38-7a25-4ac1-816e-8668a9931c76', [54.61,33.655], [54.60,33.60], 'Clear copper legend'),
        ('765944d6-e3f8-4d5f-b6aa-59b692eb0145', [62.36,30.82], [62.28,30.82], 'Clear VSTOR via'),
    ]:
        t = items[uid]
        assert xy(t.GetPosition()) == old
        t.SetPosition(vec(*new))
        ledger.append(dict(uuid=uid, action='move_via', before=old, after=new, reason=reason))
    for uid, start, end in [
        ('9995804e-9dd0-447a-8b48-98c72382f0d4', [63.801,30.82], [62.28,30.82]),
        ('4bb3e988-fb4a-42c0-a382-95c54a3c3553', [61.72,30.26], [62.28,30.82]),
        ('ef34b86d-2919-4d1f-bd70-e01aa36508f9', [58.31,30.26], [61.72,30.26]),
    ]:
        t = items[uid]
        ledger.append(dict(uuid=uid, action='adjust_via_approach', before=[xy(t.GetStart()),xy(t.GetEnd())], after=[start,end]))
        t.SetStart(vec(*start)); t.SetEnd(vec(*end))
    for uid, reason in [
        ('a970a386-981e-406c-a7f5-fce956817c45', 'Entire copper is contained in retained GNSS vertical trace'),
        ('d6ac3fd9-9dbd-4382-9f6b-eb971d13ee72', 'Unused rear via connection; retain both front supply traces into their supply zone'),
    ]:
        b.Remove(items[uid])
        ledger.append(dict(uuid=uid, action='delete_redundant_item', reason=reason))
    refs = {f.GetReference(): f for f in b.GetFootprints()}
    base_refs = {f.GetReference(): f for f in baseline.GetFootprints()}
    for ref in ('C22','C23','R24','R25','R26','R27','U8'):
        assert refs[ref].GetPath().AsString() in ('','/')
        refs[ref].SetPath(base_refs[ref].GetPath())
        ledger.append(dict(ref=ref, action='restore_schematic_uuid_path', path=refs[ref].GetPath().AsString()))
    for ref in ('J1','J2','J20'):
        refs[ref].SetAttributes(base_refs[ref].GetAttributes())
        ledger.append(dict(ref=ref, action='restore_manual_assembly_attributes'))
    # Connect the isolated pressure-sensor ground locally on both copper faces.
    via = pcbnew.PCB_VIA(b)
    via.SetPosition(vec(68.75,59.95)); via.SetWidth(pcbnew.FromMM(.6))
    via.SetDrill(pcbnew.FromMM(.3))
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetNet(b.FindNet('GND')); b.Add(via)
    ledger.append(dict(uuid=via.m_Uuid.AsString(), action='add_ground_stitch', at=[68.75,59.95], reason='Join U4/C11 ground island'))
    pcbnew.SaveBoard(str(path), b)
    (a.project/'repair-ledger.json').write_text(json.dumps(dict(input_sha256=before,output_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),changes=ledger),indent=2)+'\n')

if __name__ == '__main__':
    main()
