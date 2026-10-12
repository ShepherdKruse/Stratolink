#!/usr/bin/env python3
"""Independent TMP117 check using native KiCad connectivity and fresh netlist.

Run with KiCad's bundled Python. Read-only toward the CAD; writes JSON beside
this script. The expected map comes from TI SNOSD82D, Table 5-1, not the ECO.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET

import pcbnew

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EXPECTED = {
    'A1': ('SDA', 'SDA', 'bidirectional'),
    'A2': ('SCL', 'SCL', 'input'),
    'B1': ('V+', '+3.3V', 'power_in'),
    'B2': ('GND', 'GND', 'power_in'),
    'C1': ('ADD0', 'GND', 'input'),
    'C2': ('ALERT', 'GND', 'open_collector'),
}


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


def descendants(item, kind):
    result = []
    for sub in item:
        if isinstance(sub, list):
            if sub and sub[0] == kind:
                result.append(sub)
            result.extend(descendants(sub, kind))
    return result


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--project', type=Path, default=ROOT/'hardware/pcb/stratolink')
    ap.add_argument('--baseline-git', default='f0fe2a060b50d3df19777e43e43ab3eb63cfbb47',
                    help='Frozen v1 Git revision for this initial TMP117 ECO check')
    ap.add_argument('--output-dir', type=Path, default=HERE.parent/'promotion')
    args = ap.parse_args()
    base = args.project
    # Path.with_suffix would replace the literal version suffix if the basename
    # itself ends in v1.1, so append the KiCad extensions explicitly instead.
    board_path = Path(str(base) + '.kicad_pcb')
    sch_path = Path(str(base) + '.kicad_sch')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    xml_path = args.output_dir/'independent-netlist.xml'
    subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format', 'kicadxml',
                    '--output', str(xml_path), str(sch_path)], check=True)
    xml = ET.parse(xml_path)
    schematic_map = {}
    for net in xml.findall('.//nets/net'):
        for pad in net.findall('node'):
            if pad.get('ref') == 'U5':
                schematic_map[pad.get('pin')] = {
                    'net': net.get('name'), 'pintype': pad.get('pintype'),
                    'function': pad.get('pinfunction'),
                }
    sch = parse(sch_path.read_text())
    lib_symbols = nodes(sch, 'lib_symbols')[0]
    embedded = next(s for s in nodes(lib_symbols, 'symbol') if 'TMP117' in s[1])
    embedded_map = {field(p, 'number'): (field(p, 'name'), p[1])
                    for p in descendants(embedded, 'pin')}
    local_symbols = list(base.parent.glob('**/*TMP117*.kicad_sym'))
    local_maps = {}
    for path in local_symbols:
        local_maps[str(path.relative_to(ROOT))] = {
            field(p, 'number'): (field(p, 'name'), p[1])
            for p in descendants(parse(path.read_text()), 'pin')
        }
    board = pcbnew.LoadBoard(str(board_path))
    conn = board.GetConnectivity()
    baseline_temp = tempfile.TemporaryDirectory(prefix='stratolink-v1-reference-')
    baseline_path = Path(baseline_temp.name)/'stratolink.kicad_pcb'
    baseline_path.write_bytes(subprocess.check_output(
        ['git', 'show', args.baseline_git+':hardware/pcb/stratolink.kicad_pcb'], cwd=ROOT))
    baseline = pcbnew.LoadBoard(str(baseline_path))
    def vector(v):
        return (v.x, v.y)
    def geometry(board_object):
        result = {}
        for f in board_object.GetFootprints():
            pads = []
            for p in f.Pads():
                pads.append((p.m_Uuid.AsString(), p.GetNumber(), vector(p.GetPosition()),
                             vector(p.GetSize()), vector(p.GetDrillSize()), p.GetShape(),
                             p.GetOrientationDegrees(), p.GetLayerSet().FmtHex()))
            result[f.GetReference()] = {
                'position_nm': vector(f.GetPosition()), 'rotation_deg': f.GetOrientationDegrees(),
                'layer': f.GetLayer(), 'pads': sorted(pads),
            }
        return result
    original_geometry = geometry(baseline)
    actual_geometry = geometry(board)
    assert original_geometry == actual_geometry, 'Footprint or pad geometry changed'
    source_hashes = json.loads((ROOT/'analysis/v1_1_layout_20261012/pcb_audit/source_hashes.json').read_text())
    for rel, expected_sha in source_hashes.items():
        blob = subprocess.check_output(['git', 'show', args.baseline_git+':'+rel], cwd=ROOT)
        assert hashlib.sha256(blob).hexdigest() == expected_sha, ('Git baseline differs', rel)
    def other_pad_nets(board_object):
        return {(f.GetReference(), p.GetNumber()): p.GetNetname()
                for f in board_object.GetFootprints() if f.GetReference() != 'U5'
                for p in f.Pads()}
    original_other_nets = other_pad_nets(baseline)
    actual_other_nets = other_pad_nets(board)
    assert original_other_nets == actual_other_nets, 'Non-U5 pad/net assignments changed'
    u5 = next(f for f in board.GetFootprints() if f.GetReference() == 'U5')
    rows = []
    for p in u5.Pads():
        ball = p.GetNumber()
        function, net, kind = EXPECTED[ball]
        joined = sorted((q.GetParentFootprint().GetReference(), q.GetNumber())
                        for q in conn.GetConnectedItems(p) if isinstance(q, pcbnew.PAD))
        row = {
            'ball': ball, 'expected': {'function': function, 'net': net, 'type': kind},
            'board_net': p.GetNetname(), 'board_function': p.GetPinFunction(),
            'board_type': p.GetPinType(), 'embedded_symbol': embedded_map[ball],
            'schematic_netlist': schematic_map[ball], 'connected_pads': joined,
        }
        assert p.GetNetname() == net, row
        assert p.GetPinFunction() == function, row
        assert p.GetPinType() == kind, row
        assert embedded_map[ball] == (function, kind), row
        assert schematic_map[ball]['net'] == net, row
        assert schematic_map[ball]['pintype'] == kind, row
        for local in local_maps.values():
            assert local[ball] == (function, kind), (ball, local[ball])
        required = {'A1': ('U2', '10'), 'A2': ('U2', '9'),
                    'B1': ('C12', '2'), 'B2': ('C12', '1'),
                    'C1': ('C12', '1'), 'C2': ('C12', '1')}[ball]
        assert required in joined, (ball, 'missing physical connectivity', required, joined)
        rows.append(row)
    assert len(rows) == 6
    assert local_maps, 'No project-local corrected TMP117 symbol found'
    result = {
        'status': 'pass', 'scope': 'TMP117 symbol, netlist, pad metadata and native copper connectivity',
        'kicad_version': pcbnew.GetBuildVersion(), 'source': 'TI SNOSD82D p4 and p33',
        'files': {str(p.relative_to(ROOT)): sha(p) for p in [board_path, sch_path, *local_symbols]},
        'project_local_symbols': local_maps,
        'unchanged_non_u5_pad_nets': len(actual_other_nets),
        'unchanged_footprint_count': len(actual_geometry),
        'unchanged_pad_geometry_count': sum(len(f['pads']) for f in actual_geometry.values()),
        'original_sources_preserved_in_git': source_hashes,
        'baseline_git_commit': args.baseline_git,
        'baseline_board_sha256': sha(baseline_path),
        'whole_board_unconnected_count': conn.GetUnconnectedCount(False),
        'pads': rows,
    }
    (args.output_dir/'electrical_check.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({'status': result['status'], 'pad_checks': len(rows),
                      'whole_board_unconnected_count': result['whole_board_unconnected_count']}))


if __name__ == '__main__':
    main()
