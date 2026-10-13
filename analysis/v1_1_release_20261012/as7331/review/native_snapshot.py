#!/usr/bin/env python3
"""Read-only native snapshots for independent AS7331 board review.

Run with KiCad's bundled Python. A saved CLI-refilled analysis copy supplies project-aware filled zones; input
source hashes must remain unchanged. Output is evidence, never modified CAD.
"""
import argparse,hashlib,json,sys
from pathlib import Path
import pcbnew,wx

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'analysis/v1_1_solar_attachments_20261012/review'))
import check_solar_attachments as sx

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def mm(v): return [round(pcbnew.ToMM(v.x),6),round(pcbnew.ToMM(v.y),6)]
def key(p): return p.GetParentFootprint().GetReference()+'.'+p.GetNumber()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--project',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--refilled-pcb',type=Path,required=True);a=ap.parse_args()
    paths={str(p.relative_to(a.project)):sha(p) for p in a.project.rglob('*') if p.is_file() and (p.suffix in {'.kicad_pcb','.kicad_sch','.kicad_pro','.kicad_dru','.kicad_mod','.kicad_sym'} or p.name.endswith('lib-table'))}
    fill=json.loads((a.refilled_pcb.parent/'manifest.json').read_text());assert fill['source_hashes']['stratolink.kicad_pcb']==paths['stratolink.kicad_pcb'];assert sha(a.refilled_pcb)==fill['refilled_pcb_sha256']
    app=wx.App(False);b=pcbnew.LoadBoard(str(a.refilled_pcb))
    b.BuildConnectivity();c=b.GetConnectivity()
    foots={};pads={};physical_pads={}
    for f in b.GetFootprints():
        ref=f.GetReference();foots[ref]=dict(value=f.GetValue(),footprint=str(f.GetFPID().GetLibNickname())+":"+str(f.GetFPID().GetLibItemName()),at=mm(f.GetPosition()),angle=f.GetOrientationDegrees(),layer=f.GetLayerName(),uuid=f.m_Uuid.AsString(),pads=[])
        for p in f.Pads():
            physical={key(p)}|{key(x) for x in c.GetConnectedItems(p) if isinstance(x,pcbnew.PAD)}
            rec=dict(uuid=p.m_Uuid.AsString(),net=p.GetNetname(),at=mm(p.GetPosition()),local=mm(p.GetFPRelativePosition()),size=mm(p.GetSize()),angle=p.GetOrientationDegrees(),drill=mm(p.GetDrillSize()),shape=p.GetShape(),layers=p.GetLayerSet().FmtHex(),effective_paste_margin_mm=mm(p.GetSolderPasteMargin(pcbnew.F_Paste)),paste_margin_mm=None if p.GetLocalSolderPasteMargin() is None else pcbnew.ToMM(p.GetLocalSolderPasteMargin()),physical=sorted(physical))
            pads[key(p)]=rec;physical_pads[p.m_Uuid.AsString()]={**rec,'key':key(p),'physical_uuids':sorted({p.m_Uuid.AsString()}|{x.m_Uuid.AsString() for x in c.GetConnectedItems(p) if isinstance(x,pcbnew.PAD)})};foots[ref]['pads'].append(p.GetNumber())
    tracks={t.m_Uuid.AsString():dict(start=mm(t.GetStart()),end=mm(t.GetEnd()),width=pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu) if isinstance(t,pcbnew.PCB_VIA) else t.GetWidth()),net=t.GetNetname(),layer=t.GetLayerName(),kind=t.GetClass()) for t in b.GetTracks()}
    raw=sx.parse((a.project/'stratolink.kicad_pcb').read_text());raw_track_nets={sx.field(n,'uuid'):sx.field(n,'net') for n in raw if isinstance(n,list) and n[0] in ['segment','arc','via']}
    assert set(tracks)==set(raw_track_nets), 'CLI fill changed track/via membership'
    for ident,net in raw_track_nets.items():assert tracks[ident]['net']==net, ('Native/CLI inferred a different net from explicit source',ident,net,tracks[ident]['net'])
    for t in b.GetTracks():
        if isinstance(t,pcbnew.PCB_ARC):tracks[t.m_Uuid.AsString()]['mid']=mm(t.GetMid())
        if isinstance(t,pcbnew.PCB_VIA):tracks[t.m_Uuid.AsString()].update(drill=pcbnew.ToMM(t.GetDrillValue()),via_type=t.GetViaType())
    result=dict(raw_source_track_and_via_net_names_match_native=True,project_aware_refill_manifest=fill,source=str(a.project),hashes=paths,footprints=foots,pads=pads,physical_pads=physical_pads,tracks=tracks,unconnected_native=c.GetUnconnectedCount(False))
    for n,v in paths.items():assert sha(a.project/n)==v,('Input changed during read-only snapshot',n)
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':'PASS','snapshot':str(a.output),'footprints':len(foots),'physical_pads':len(physical_pads),'distinct_ref_pad_names':len(pads),'unconnected':result['unconnected_native']}))

if __name__=='__main__':main()
