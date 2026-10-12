#!/usr/bin/env python3
"""Independent read-only solar-anchor regression review using native KiCad.

Frozen baseline is Git 1aed52f. Run with KiCad's bundled Python, e.g.:
  python3.9 check_solar_attachments.py --board /candidate/stratolink.kicad_pcb \
      --schematic /candidate/stratolink.kicad_sch --outdir /review/results

No candidate or canonical CAD is modified. The baseline CAD/netlist live only
under ai-working/scratch; output contains hashes and verification evidence.
"""
from pathlib import Path
import argparse
import collections
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET

import pcbnew
import wx

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASELINE = '1aed52ff7af3d27aef6ff4b0ceba710c57dc6865'
SOLAR_REFS = {'J1', 'J2'}
REMOVED_SIDE_HOLES = {'b57f7e15-55af-43e4-af2a-f9420f7a2737',
                      '0f92e152-acae-4962-8e59-676ddaeed576'}
MIC_NC = {('U2', '31'), ('U2', '32')}


def parse(text):
    stack, root = [], None
    for token in re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+', text):
        if token == '(':
            item = []
            if stack:
                stack[-1].append(item)
            else:
                root = item
            stack.append(item)
        elif token == ')':
            stack.pop()
        else:
            stack[-1].append(json.loads(token) if token.startswith('"') else token)
    assert not stack
    return root


def nodes(item, kind):
    return [x for x in item if isinstance(x, list) and x and x[0] == kind]


def field(item, name):
    found = nodes(item, name)
    return found[0][1] if found else None


def prop(item, name):
    return next((x[2] for x in nodes(item, 'property') if x[1] == name), None)


def keyed(items):
    return {field(item, 'uuid'): item for item in items}


def key(pad):
    return pad.GetParentFootprint().GetReference(), pad.GetNumber()


def pad_groups(board):
    result = collections.defaultdict(list)
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            result[key(pad)].append(pad)
    return result


def node_netlist(path):
    result = {}
    for net in ET.parse(path).findall('.//nets/net'):
        for node in net.findall('node'):
            itemkey = node.get('ref'), node.get('pin')
            assert itemkey not in result, ('Duplicated schematic node', itemkey)
            result[itemkey] = (net.get('name'), node.get('pintype'), node.get('pinfunction'))
    return result


def export_netlist(path, output):
    result = subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format', 'kicadxml',
                             '--output', str(output), str(path)],
                            check=True, text=True, capture_output=True)
    output.with_suffix('.log').write_text(result.stdout + result.stderr)


def connected_keys(connectivity, pad):
    # Include the starting logical node explicitly. Otherwise splitting one ground
    # land into several physical pads with the same number changes self-membership.
    result = {key(pad)}
    result.update(key(item) for item in connectivity.GetConnectedItems(pad)
                  if isinstance(item, pcbnew.PAD))
    return result


def poly_summary(board):
    outlines = pcbnew.SHAPE_POLY_SET()
    good = board.GetBoardPolygonOutlines(outlines, False, None, False, False)
    pts = []
    for i in range(outlines.OutlineCount()):
        chain = outlines.Outline(i)
        pts.extend((chain.CPoint(j).x / 1e6, chain.CPoint(j).y / 1e6)
                   for j in range(chain.PointCount()))
    return {'valid': bool(good), 'outline_count': outlines.OutlineCount(),
            'hole_count': sum(outlines.HoleCount(i) for i in range(outlines.OutlineCount())),
            'net_area_mm2': outlines.Area() / 1e12,
            'bounds_mm': [min(x for x,y in pts), min(y for x,y in pts),
                          max(x for x,y in pts), max(y for x,y in pts)] if pts else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--board', type=Path, required=True)
    parser.add_argument('--schematic', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    parser.add_argument('--allow-baseline-outline', action='store_true',
                        help='Checker self-test: permit unchanged outline without the solar notches')
    args = parser.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)
    before_hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in (args.board, args.schematic)}
    baseline = Path.home() / 'Repositories/ai-working/scratch/stratolink-solar-review/baseline'
    baseline.mkdir(parents=True, exist_ok=True)
    for extension in ('kicad_pcb','kicad_sch','kicad_pro'):
        path = baseline / ('stratolink.' + extension)
        expected = subprocess.check_output(['git','show',BASELINE+':hardware/pcb/'+path.name], cwd=ROOT)
        if path.exists():
            assert path.read_bytes() == expected, ('Frozen baseline changed', str(path))
        else:
            path.write_bytes(expected)
    if not (baseline / 'netlist.xml').exists():
        export_netlist(baseline/'stratolink.kicad_sch', baseline/'netlist.xml')
    export_netlist(args.schematic, args.outdir/'candidate-netlist.xml')
    ot, nt = (parse(path.read_text()) for path in (baseline/'stratolink.kicad_pcb', args.board))
    ofp, nfp = ({prop(f,'Reference'):f for f in nodes(tree,'footprint')} for tree in (ot,nt))
    assert set(ofp) == set(nfp), ('Reference set changed', set(ofp)-set(nfp),set(nfp)-set(ofp))
    retained = sorted(set(ofp)-SOLAR_REFS)
    changed_retained = [r for r in retained if ofp[r] != nfp[r]]
    assert not changed_retained, ('Retained footprint geometry or metadata changed', changed_retained)
    assert not {'MK1','R20','C13'} & set(nfp), 'Removed mic parts returned'
    # All board graphics except the intended outline and label additions stay exact.
    # Explicit label changes are reported for human review, never allowed silently.
    board_graphics = {}
    for tree, label in ((ot,'before'),(nt,'after')):
        board_graphics[label] = keyed([o for o in tree if isinstance(o,list)
                                      and o[0].startswith('gr_') and o[0] != 'gr_text'
                                      and field(o,'layer') != 'Edge.Cuts'])
    assert board_graphics['before'] == board_graphics['after'], 'Non-outline board graphics changed'
    oldtext,newtext = keyed(nodes(ot,'gr_text')),keyed(nodes(nt,'gr_text'))
    graphics_text_delta = {'removed': [oldtext[k] for k in oldtext if k not in newtext],
                           'added': [newtext[k] for k in newtext if k not in oldtext],
                           'changed': [{'before':oldtext[k],'after':newtext[k]} for k in oldtext.keys() & newtext.keys() if oldtext[k]!=newtext[k]]}
    osch,nsch=(parse(p.read_text()) for p in (baseline/'stratolink.kicad_sch',args.schematic))
    oss,nss=({prop(s,'Reference'):s for s in nodes(tree,'symbol')} for tree in (osch,nsch))
    assert set(oss)==set(nss), 'Schematic reference set changed'
    assert all(oss[r]==nss[r] for r in oss if r not in SOLAR_REFS), 'Other schematic symbol changed'
    def strip_metadata(symbol):
        return [x for x in symbol if not (isinstance(x,list) and x and x[0] in
                                          {'property','in_bom','dnp','exclude_from_sim'})]
    assert all(strip_metadata(oss[r])==strip_metadata(nss[r]) for r in SOLAR_REFS), 'Solar symbol electrical structure changed'
    for kind in ('lib_symbols','wire','junction','no_connect','label','global_label','hierarchical_label','bus','bus_entry'):
        assert nodes(osch,kind)==nodes(nsch,kind), ('Schematic electrical objects changed',kind)
    def fixed_schematic(tree):
        return [x for x in tree if not (isinstance(x,list) and x and x[0] in {'symbol','text'})]
    assert fixed_schematic(osch)==fixed_schematic(nsch), 'Other schematic structure or graphics changed'
    old_netlist,new_netlist=node_netlist(baseline/'netlist.xml'),node_netlist(args.outdir/'candidate-netlist.xml')
    assert old_netlist==new_netlist, ('Schematic node nets or pin roles changed',
                                     [(k,old_netlist.get(k),new_netlist.get(k)) for k in old_netlist.keys()|new_netlist.keys() if old_netlist.get(k)!=new_netlist.get(k)])
    schtexts = {'before':keyed(nodes(osch,'text')), 'after':keyed(nodes(nsch,'text'))}
    schematic_text_delta = {'removed':[v for k,v in schtexts['before'].items() if k not in schtexts['after']],
                             'added':[v for k,v in schtexts['after'].items() if k not in schtexts['before']],
                             'changed':[{'before':schtexts['before'][k],'after':schtexts['after'][k]} for k in schtexts['before'].keys() & schtexts['after'].keys() if schtexts['before'][k]!=schtexts['after'][k]]}

    app = wx.App(False)
    old,new=pcbnew.LoadBoard(str(baseline/'stratolink.kicad_pcb')),pcbnew.LoadBoard(str(args.board))
    og,ng=pad_groups(old),pad_groups(new)
    assert set(og)==set(ng), ('Logical PCB pad keys changed',sorted(set(og)-set(ng)),sorted(set(ng)-set(og)))
    oc,nc=old.GetConnectivity(),new.GetConnectivity()
    checked,details=0,[]
    for node in sorted(ng):
        oldnets={p.GetNetname() for p in og[node]}
        newnets={p.GetNetname() for p in ng[node]}
        assert oldnets==newnets, ('Logical pad net changed',node,oldnets,newnets)
        expected = [connected_keys(oc,p) for p in og[node]]
        # Existing multi-pad nodes such as ground pads must already share their
        # copper island, or each retained physical pad is compared by UUID below.
        if node[0] in SOLAR_REFS:
            assert all(c==expected[0] for c in expected), ('Baseline solar pin already split',node)
            for p in ng[node]:
                observed=connected_keys(nc,p)
                assert observed==expected[0], ('Solar physical island lost/gained connectivity',node,p.m_Uuid.AsString(),sorted(expected[0]-observed),sorted(observed-expected[0]))
                details.append({'ref':node[0],'pin':node[1],'uuid':p.m_Uuid.AsString(),
                                'net':p.GetNetname(),'connected_logical_nodes':len(observed)})
                checked+=1
        else:
            old_by_uuid={p.m_Uuid.AsString():p for p in og[node]}
            for p in ng[node]:
                oldp=old_by_uuid[p.m_Uuid.AsString()]
                expected_set=connected_keys(oc,oldp)
                observed=connected_keys(nc,p)
                assert expected_set==observed, ('Retained physical connectivity changed',node,p.m_Uuid.AsString(),sorted(expected_set-observed),sorted(observed-expected_set))
                checked+=1
        if node in MIC_NC:
            for p in ng[node]:
                others=[i for i in nc.GetConnectedItems(p) if i.m_Uuid.AsString()!=p.m_Uuid.AsString()]
                assert not others, ('Mic NC pad acquired copper connection',node)
                assert p.GetNetname().startswith('unconnected-'), ('Mic pad lost NC net',node)
    assert nc.GetUnconnectedCount(False)==0, ('Native open connection count',nc.GetUnconnectedCount(False))

    oldoutline,newoutline=poly_summary(old),poly_summary(new)
    assert newoutline['valid'] and newoutline['outline_count']==1, 'Invalid/disjoint board outline'
    assert all(abs(a-b)<.005 for a,b in zip(oldoutline['bounds_mm'],newoutline['bounds_mm'])), 'Board outer dimensions changed'
    oldedge=keyed([x for x in ot if isinstance(x,list) and field(x,'layer')=='Edge.Cuts'])
    newedge=keyed([x for x in nt if isinstance(x,list) and field(x,'layer')=='Edge.Cuts'])
    if not args.allow_baseline_outline:
        assert REMOVED_SIDE_HOLES <= oldedge.keys(), 'Expected baseline side holes not found'
        assert not REMOVED_SIDE_HOLES & newedge.keys(), 'Old side mounting holes remain'
        assert oldoutline['hole_count']==4 and newoutline['hole_count']==2, ('Unexpected routed internal cutout count',oldoutline,newoutline)
        assert oldedge!=newedge, 'Solar notches absent'
        assert len(newedge)>len(oldedge)-2, 'No new edge segments for solar notches'
    after_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.board,args.schematic)}
    assert before_hashes==after_hashes, 'Candidate changed during review'
    result={'status':'pass','baseline_commit':BASELINE,'kicad_version':pcbnew.GetBuildVersion(),
            'candidate_sha256':after_hashes,'retained_exact_footprints':retained,'footprints_count':len(nfp),
            'logical_pad_keys':len(ng),'physical_pad_connectivity_checks':checked,
            'schematic_node_nets_compared':len(new_netlist),'solar_physical_pad_islands':details,
            'native_unconnected_count':nc.GetUnconnectedCount(False),'TMP117_exact_footprint_preserved':ofp['U5']==nfp['U5'],
            'mic_unconnected_pads_preserved':True,'outline_before':oldoutline,'outline_after':newoutline,
            'board_text_changes_for_human_review':graphics_text_delta,
            'schematic_text_changes_for_human_review':schematic_text_delta,
            'mode':'baseline_self_test' if args.allow_baseline_outline else 'candidate_review'}
    (args.outdir/'comparison.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('retained_exact_footprints','board_text_changes_for_human_review','schematic_text_changes_for_human_review')},indent=2))


if __name__=='__main__':
    main()
