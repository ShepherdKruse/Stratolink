#!/usr/bin/env python3
"""Read-only independent mic-removal regression check; use KiCad Python."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET

import pcbnew

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = HERE/'baseline'
CURRENT = ROOT/'hardware/pcb'
REMOVED = {'MK1', 'C13', 'R20'}
DISCONNECTED = {('U2', '31'), ('U2', '32')}
SIGNALS = {'PDM', 'CLK', 'Net-(MK1-CLK)'}
BASELINE_COMMIT = '38de8d750c476258ba217c76274216863cf0b29c'


def parse(text):
    stack = []
    root = None
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


def nodekey(pad):
    return (pad.GetParentFootprint().GetReference(), pad.GetNumber())


def pads(board):
    return {nodekey(p): p for f in board.GetFootprints() for p in f.Pads()
            if f.GetReference() not in REMOVED}


def getnetlist(path):
    xml = ET.parse(path)
    result = {}
    for net in xml.findall('.//nets/net'):
        for pad in net.findall('node'):
            key = pad.get('ref'), pad.get('pin')
            if key[0] not in REMOVED and key not in DISCONNECTED:
                result[key] = (net.get('name'), pad.get('pintype'), pad.get('pinfunction'))
    return result


def main():
    BASE.mkdir(parents=True, exist_ok=True)
    for extension in ['kicad_pcb', 'kicad_sch', 'kicad_pro']:
        path = BASE/('stratolink.'+extension)
        expected = subprocess.check_output(
            ['git', 'show', BASELINE_COMMIT+':hardware/pcb/'+path.name], cwd=ROOT)
        if not path.exists():
            path.write_bytes(expected)
        assert path.read_bytes() == expected, ('Frozen baseline differs from Git', path)
    if not (BASE/'netlist.xml').exists():
        subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format', 'kicadxml',
                        '--output', str(BASE/'netlist.xml'), str(BASE/'stratolink.kicad_sch')],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format', 'kicadxml',
                    '--output', str(HERE/'netlist.xml'), str(CURRENT/'stratolink.kicad_sch')],
                   check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    oldtree = parse((BASE/'stratolink.kicad_pcb').read_text())
    newtree = parse((CURRENT/'stratolink.kicad_pcb').read_text())
    oldfp = {prop(f, 'Reference'): f for f in nodes(oldtree, 'footprint')}
    newfp = {prop(f, 'Reference'): f for f in nodes(newtree, 'footprint')}
    assert set(oldfp)-set(newfp) == REMOVED
    assert not set(newfp)-set(oldfp)
    # Pad net changes on the two newly NC MCU pins are the only permitted
    # remaining-footprint changes. Compare entire other footprints verbatim.
    assert all(oldfp[r] == newfp[r] for r in newfp if r != 'U2'), 'Retained footprint changed'
    def without_nc_nets(f):
        copy = json.loads(json.dumps(f))
        for p in nodes(copy, 'pad'):
            if p[1] in {'31', '32'}:
                p[:] = [x for x in p if not (isinstance(x, list) and x[0] in {'net', 'pintype'})]
        return copy
    assert without_nc_nets(oldfp['U2']) == without_nc_nets(newfp['U2']), 'Unrelated U2 geometry changed'
    for kind in ['gr_line', 'gr_arc', 'gr_circle', 'gr_poly']:
        assert nodes(oldtree, kind) == nodes(newtree, kind), ('Board graphics changed', kind)
    for item in nodes(newtree, 'segment')+nodes(newtree, 'via'):
        assert field(item, 'net') not in SIGNALS, ('Mic copper remains', item)
    oldsch = parse((BASE/'stratolink.kicad_sch').read_text())
    newsch = parse((CURRENT/'stratolink.kicad_sch').read_text())
    oldsymbols = {prop(s, 'Reference'): s for s in nodes(oldsch, 'symbol')}
    newsymbols = {prop(s, 'Reference'): s for s in nodes(newsch, 'symbol')}
    assert set(oldsymbols)-set(newsymbols) == REMOVED|{'#PWR033', '#PWR034'}
    assert not set(newsymbols)-set(oldsymbols)
    assert all(oldsymbols[r] == newsymbols[r] for r in newsymbols), 'Retained schematic symbol changed'
    for kind in ['global_label', 'label', 'hierarchical_label']:
        assert all(label[1] not in {'CLK', 'PDM'} for label in nodes(newsch, kind))
    assert getnetlist(BASE/'netlist.xml') == getnetlist(HERE/'netlist.xml'), 'Other schematic nets changed'
    old = pcbnew.LoadBoard(str(BASE/'stratolink.kicad_pcb'))
    new = pcbnew.LoadBoard(str(CURRENT/'stratolink.kicad_pcb'))
    op, np = pads(old), pads(new)
    assert set(op) == set(np)
    oc, nc = old.GetConnectivity(), new.GetConnectivity()
    checked = 0
    ncrows = []
    for key in sorted(np):
        if key in DISCONNECTED:
            items = list(nc.GetConnectedItems(np[key]))
            others = [x for x in items if x.m_Uuid.AsString() != np[key].m_Uuid.AsString()]
            assert not others, ('NC MCU pad still physically connected', key)
            assert np[key].GetNetname() not in SIGNALS
            ncrows.append({'ref': key[0], 'pin': key[1], 'net': np[key].GetNetname(), 'connected_other_items': len(others)})
            continue
        assert op[key].GetNetname() == np[key].GetNetname(), ('Other pad net changed', key)
        def connected(conn, pad):
            return {nodekey(x) for x in conn.GetConnectedItems(pad) if isinstance(x, pcbnew.PAD)
                    and nodekey(x)[0] not in REMOVED and nodekey(x) not in DISCONNECTED}
        old_connections, new_connections = connected(oc, op[key]), connected(nc, np[key])
        assert old_connections == new_connections, (
            'Remaining physical connectivity changed', key,
            sorted(old_connections-new_connections), sorted(new_connections-old_connections))
        checked += 1
    assert nc.GetUnconnectedCount(False) == 0
    result = {
        'status': 'pass', 'baseline_commit': '38de8d7',
        'removed_references': sorted(REMOVED),
        'remaining_footprints': len(newfp),
        'remaining_pad_connectivity_checks': checked,
        'new_nc_mcu_pads': ncrows,
        'remaining_schematic_net_nodes': len(getnetlist(HERE/'netlist.xml')),
        'tmp117_footprint_and_all_retained_components_unchanged': True,
        'whole_board_unconnected_count': nc.GetUnconnectedCount(False),
        'files_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in [CURRENT/'stratolink.kicad_pcb', CURRENT/'stratolink.kicad_sch']},
    }
    (HERE/'comparison.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
