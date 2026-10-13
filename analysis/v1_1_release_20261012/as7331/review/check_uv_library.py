#!/usr/bin/env python3
"""Verify project-local AS7331 symbol/footprint against primary-source pin semantics."""
from pathlib import Path
import argparse,hashlib,json,sys
import pcbnew,wx
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'analysis/v1_1_solar_attachments_20261012/review'))
import check_solar_attachments as sx

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--candidate',type=Path,required=True);a=ap.parse_args();app=wx.App(False)
    sp=a.candidate/'lib/Stratolink_UV.kicad_sym';fp=a.candidate/'lib/Stratolink_v1p1_U6_AS7331_OLGA16.kicad_mod';board=a.candidate/'stratolink.kicad_pcb'
    symbol=sx.nodes(sx.parse(sp.read_text()),'symbol')[0];pins={}
    for unit in sx.nodes(symbol,'symbol'):
        for p in sx.nodes(unit,'pin'):pins[sx.field(p,'number')]=dict(name=sx.field(p,'name'),type=p[1])
    expected={'1':('VSSA','power_in'),'2':('VSSA','power_in'),'3':('VDDA','power_in'),'4':('REXT','passive'),'5':('VSSA','power_in'),'6':('VSSA','power_in'),'7':('A1','input'),'8':('SYN','input'),'9':('READY','output'),'10':('VDDD','power_in'),'11':('VSSD','power_in'),'12':('SDA','bidirectional'),'13':('SCL','input'),'14':('A0','input'),'15':('VSSA','power_in'),'16':('VSSA','power_in')}
    assert pins=={n:dict(name=name,type=typ) for n,(name,typ) in expected.items()}
    b=pcbnew.LoadBoard(str(board));u6=next(f for f in b.GetFootprints() if f.GetReference()=='U6');lib=pcbnew.FootprintLoad(str(fp.parent),fp.stem)
    def data(f):return {p.GetNumber():dict(local_mm=[p.GetFPRelativePosition().x/1e6,p.GetFPRelativePosition().y/1e6],size_mm=[p.GetSize().x/1e6,p.GetSize().y/1e6],shape=p.GetShape(),layers=p.GetLayerSet().FmtHex(),paste=[v/1e6 for v in [p.GetSolderPasteMargin(pcbnew.F_Paste).x,p.GetSolderPasteMargin(pcbnew.F_Paste).y]]) for p in f.Pads()}
    assert data(u6)==data(lib),'Native U6 disagrees with its project-local footprint'
    result=dict(status='PASS',source_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [sp,fp,board]},symbol_primary_pin_semantics=pins,board_and_library_pad_geometry_match=True,footprint_pad_count=len(data(lib)))
    (HERE/'uv-library-review.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
