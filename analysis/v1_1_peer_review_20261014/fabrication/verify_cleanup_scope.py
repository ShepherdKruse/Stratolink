#!/usr/bin/env python3
"""Independent read-only scope check of the local copper/lettering cleanup."""
from pathlib import Path
import sys,json,hashlib,argparse
import pcbnew,wx
ROOT=Path(__file__).resolve().parents[3];H=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'analysis/v1_1_solar_attachments_20261012/review'))
import check_solar_attachments as a
args=argparse.ArgumentParser();args.add_argument('--candidate',type=Path,required=True);args.add_argument('--name',required=True);args=args.parse_args()
paths=[ROOT/'hardware/pcb/stratolink.kicad_pcb',args.candidate];raws=[p.read_bytes()for p in paths];trees=[a.parse(raw.decode())for raw in raws];app=wx.App(False);boards=[pcbnew.LoadBoard(str(p))for p in paths]
sha=lambda b:hashlib.sha256(b).hexdigest()
for kind in ['footprint','setup','general','net','gr_line','gr_arc','gr_rect','via']:
 assert a.nodes(trees[0],kind)==a.nodes(trees[1],kind),('Unapproved invariant difference',kind)
tracks=[{t.m_Uuid.AsString():t for t in b.GetTracks()}for b in boards]
def track(t):return {'net':t.GetNetname(),'layer':t.GetLayerName(),'kind':t.GetClass(),'start':list(t.GetStart()),'end':list(t.GetEnd()),'width':t.GetWidth(pcbnew.F_Cu) if isinstance(t,pcbnew.PCB_VIA) else t.GetWidth()}
assert not tracks[0].keys()-tracks[1].keys()
changed={u:{'before':track(tracks[0][u]),'after':track(tracks[1][u])}for u in tracks[0]if track(tracks[0][u])!=track(tracks[1][u])}
assert set(changed)=={'f950083f-9c44-5581-b006-dd929a7699ef'}
x=changed['f950083f-9c44-5581-b006-dd929a7699ef'];assert x['before']|{'width':200000}==x['after']and x['before']['width']==150000
added={u:track(tracks[1][u])for u in tracks[1].keys()-tracks[0].keys()};assert len(added)==6
ledgers={n:json.loads((args.candidate.parent/n).read_text())for n in ['copper-fix-changes.json','fillet-changes.json','text-and-seam-changes.json']}
expected_track={c['uuid']:c for d in ledgers.values()for c in d['changes']if c['action']in ['add','add_track']}
assert set(added)==set(expected_track)
for u,d in added.items():assert d['net']==expected_track[u]['net']and d['layer']==expected_track[u]['layer']
newdraw={g.m_Uuid.AsString():g for g in boards[1].GetDrawings()}
polychecks=[]
for c in ledgers['fillet-changes.json']['changes']:
 if c['action']!='add_polygon':continue
 g=newdraw[c['uuid']];expected=c['net']if c['net']and not c['net'].startswith('ART:')else''
 assert g.GetNetname()==expected,(c['uuid'],g.GetNetname(),expected)
 assert g.GetLayerName()==c['layer']
 polychecks.append({'uuid':c['uuid'],'net':g.GetNetname(),'layer':g.GetLayerName()})
for d in ledgers['text-and-seam-changes.json']['changes']:
 if d['action']!='native_text_to_copper_outlines':continue
 g=newdraw[d['text_uuid']];assert isinstance(g,pcbnew.PCB_TEXT)and g.GetLayer()==pcbnew.F_Fab and g.GetText()==d['text']
 for u in d['glyph_uuids']:assert newdraw[u].GetNetname()==''and newdraw[u].GetLayer()==pcbnew.F_Cu
assert all(g.GetLayer()not in[pcbnew.F_SilkS,pcbnew.B_SilkS]for g in boards[1].GetDrawings())
assert raws==[p.read_bytes()for p in paths]
report={'source_sha256':sha(raws[0]),'candidate_sha256':sha(raws[1]),'footprints_structurally_identical':len(a.nodes(trees[0],'footprint')),'all_original_tracks_and_vias_retained':True,'changed_original_tracks':changed,'added_tracks':added,'new_polygon_net_checks':polychecks,'two_original_texts_retained_on_F_Fab':True,'converted_copper_glyphs_unconnected_artwork':True,'no_board_silk_graphics':True,'source_and_candidate_bytes_unchanged':True,'ledger_hashes':{n:sha((args.candidate.parent/n).read_bytes())for n in ledgers}}
(H/(args.name+'-scope.json')).write_text(json.dumps(report,indent=2)+'\n');print(report['candidate_sha256'],report['footprints_structurally_identical'],len(polychecks),'polygon net checks')
