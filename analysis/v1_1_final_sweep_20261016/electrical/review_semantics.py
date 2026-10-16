#!/usr/bin/env python3
"""Read-only checks of focused pin maps and exact native source scope."""
from pathlib import Path
import argparse
import collections
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
import pcbnew
import wx

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'analysis/v1_1_solar_attachments_20261012/review'))
import check_solar_attachments as ast

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write(name, value):
    (HERE / name).write_text(json.dumps(value, indent=2) + '\n')

def without_footprint_field_visibility(tree):
    def strip_hide(node):
        return [strip_hide(v) if isinstance(v, list) else v for v in node
                if not (isinstance(v, list) and v and v[0] == 'hide')]
    out = []
    for item in tree:
        if isinstance(item, list) and item and item[0] == 'footprint':
            item = [strip_hide(v) if isinstance(v, list) and v and v[0] == 'property' else v for v in item]
        out.append(item)
    return out

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scratch', type=Path, required=True)
    args = parser.parse_args()
    paths = {name: args.scratch / name / 'stratolink.kicad_pcb' for name in ('frozen', 'current', 'repaired')}
    trees = {name: ast.parse(path.read_text()) for name, path in paths.items()}
    footprints = {name: {ast.prop(f, 'Reference'): f for f in ast.nodes(tree, 'footprint')} for name, tree in trees.items()}
    field_changes = []
    for ref in sorted(footprints['frozen']):
        old, new = footprints['frozen'][ref], footprints['repaired'][ref]
        for key in {p[1] for f in (old, new) for p in ast.nodes(f, 'property')}:
            before = [p for p in ast.nodes(old, 'property') if p[1] == key]
            after = [p for p in ast.nodes(new, 'property') if p[1] == key]
            if before != after:
                field_changes.append({'reference': ref, 'field': key, 'before': before, 'after': after})
    source_equal_except_visibility = without_footprint_field_visibility(trees['frozen']) == without_footprint_field_visibility(trees['repaired'])
    assert source_equal_except_visibility
    uid = '56e63bbd-ec8b-4f4e-ad43-a47451d11e0e'
    segment = [s for s in ast.nodes(trees['frozen'], 'segment') if ast.field(s, 'uuid') == uid]
    assert len(segment) == 1
    assert not [s for s in ast.nodes(trees['current'], 'segment') if ast.field(s, 'uuid') == uid]
    assert [s for s in ast.nodes(trees['repaired'], 'segment') if ast.field(s, 'uuid') == uid] == segment
    repaired_without_segment = [s for s in trees['repaired'] if s != segment[0]]
    assert trees['current'] == repaired_without_segment, 'Repair changed more than the missing segment'
    write('source-scope.json', {
        'pcb_hashes': {name: sha(path) for name, path in paths.items()},
        'current_to_repaired_only_restores_segment': True,
        'segment': segment[0],
        'frozen_to_repaired_all_source_nodes_identical_except_footprint_field_visibility': True,
        'field_visibility_changes': field_changes,
        'footprint_positions_pads_tracks_vias_zones_fills_outline_models_unchanged_from_frozen': True,
    })
    xml = HERE / 'repaired.xml'
    document = ET.parse(xml)
    pins, members = {}, collections.defaultdict(set)
    for net in document.findall('./nets/net'):
        for node in net.findall('node'):
            pair = (node.get('ref'), node.get('pin'))
            assert pair not in pins
            pins[pair] = {'net': net.get('name'), 'function': node.get('pinfunction'), 'type': node.get('pintype')}
            members[net.get('name')].add(pair)
    values = {c.get('ref'): c.findtext('value') for c in document.findall('./components/comp')}
    expected = {
        'TMP117': {('U5','A1'):'SDA', ('U5','A2'):'SCL', ('U5','B1'):'+3.3V',
                   ('U5','B2'):'GND', ('U5','C1'):'GND', ('U5','C2'):'GND'},
        'storage_and_ADC': {('U1','19'):'VSTOR', ('U1','3'):'VSTOR', ('U1','6'):'VSTOR',
                   ('C3','1'):'VSTOR', ('C4','1'):'VSTOR', ('R22','1'):'VSTOR', ('J4','2'):'VSTOR',
                   ('R22','2'):'PA10', ('R23','1'):'PA10', ('R23','2'):'GND', ('U2','25'):'PA10'},
        'balancer': {('U8','1'):'/SC_BAL_OUT', ('U8','2'):'GND', ('U8','3'):'/SC_HALF_REF',
                   ('U8','4'):'/SC_BAL_OUT', ('U8','5'):'/VBAT', ('R24','1'):'/VBAT',
                   ('R24','2'):'/SC_HALF_REF', ('R25','1'):'/SC_HALF_REF', ('R25','2'):'GND',
                   ('R26','1'):'/SC_BAL_OUT', ('R26','2'):'/SC_MID', ('C22','1'):'/VBAT',
                   ('C22','2'):'GND', ('C5','1'):'/VBAT', ('C5','2'):'GND', ('C5','3'):'/SC_MID', ('U1','18'):'/VBAT'},
        'SWD_programming': {('U2','7'):'SWDIO', ('J20','2'):'SWDIO', ('U2','8'):'SWCLK',
                   ('J20','4'):'SWCLK', ('U2','22'):'RST', ('J20','3'):'RST', ('J20','1'):'+3.3V',
                   ('J20','5'):'GND', ('U2','21'):'BOOT0', ('J4','6'):'BOOT0', ('R9','2'):'BOOT0', ('R9','1'):'GND'},
        'I2C': {('U2','10'):'SDA', ('U2','9'):'SCL', ('U4','7'):'SDA', ('U4','8'):'SCL',
                   ('U5','A1'):'SDA', ('U5','A2'):'SCL', ('U6','12'):'SDA', ('U6','13'):'SCL',
                   ('U7','4'):'SDA', ('U7','1'):'SCL', ('R11','1'):'+3.3V', ('R11','2'):'SDA',
                   ('R12','1'):'+3.3V', ('R12','2'):'SCL', ('R13','2'):'SCL', ('R14','2'):'SDA',
                   ('R13','1'):'Net-(U3-SCL)', ('R14','1'):'Net-(U3-SDA)',
                   ('U3','17'):'Net-(U3-SCL)', ('U3','16'):'Net-(U3-SDA)'},
        'GNSS_UART': {('U2','4'):'TX', ('U2','5'):'RX', ('J4','4'):'TX', ('J4','5'):'RX',
                   ('R16','1'):'TX', ('R16','2'):'Net-(U3-RXD)', ('U3','3'):'Net-(U3-RXD)',
                   ('R15','1'):'RX', ('R15','2'):'Net-(U3-TXD)', ('U3','2'):'Net-(U3-TXD)'},
        'RF_feeds': {('AE1','1'):'Net-(AE1-A)', ('U2','12'):'Net-(AE1-A)', ('D1','2'):'Net-(AE1-A)',
                   ('AE2','1'):'Net-(AE2-A)', ('U3','11'):'Net-(AE2-A)', ('D3','2'):'Net-(AE2-A)',
                   ('D1','1'):'GND', ('D3','1'):'GND'},
    }
    expected_values = {'U5':'TMP117AIYBGR','U2':'RAK3172-8-SM-NI','U8':'TLV8801DBVT',
                       'R22':'1MΩ','R23':'1MΩ','R24':'4.75MΩ','R25':'4.75MΩ','R26':'22Ω','C22':'100nF',
                       'R11':'4.7kΩ','R12':'4.7kΩ','R13':'0Ω','R14':'0Ω','R15':'33Ω','R16':'33Ω','R9':'0Ω'}
    for ref, value in expected_values.items():
        assert values[ref] == value, (ref, values[ref], value)
    app = wx.App(False)
    board = pcbnew.LoadBoard(str(paths['repaired']))
    board.BuildConnectivity()
    pad_groups = ast.pad_groups(board)
    checked = {}
    for group, assignments in expected.items():
        checked[group] = []
        for pair, net in assignments.items():
            assert pins[pair]['net'] == net, (pair, pins[pair], net)
            assert {p.GetNetname() for p in pad_groups[pair]} == {net}
            connected = all(members[net] <= ast.connected_keys(board.GetConnectivity(), p) for p in pad_groups[pair])
            assert connected, (pair, net)
            checked[group].append({'ref': pair[0], 'pin': pair[1], **pins[pair],
                                   'same_net_schematic_pads_all_physically_connected': connected})
    official_tmp = {'A1':'SDA','A2':'SCL','B1':'V+','B2':'GND','C1':'ADD0','C2':'ALERT'}
    tmp = []
    for ball, function in official_tmp.items():
        assert pins[('U5',ball)]['function'] == function + '_' + ball
        pad = pad_groups[('U5', ball)][0]
        tmp.append({'ball':ball,'manufacturer_function':function,'net':pad.GetNetname(),
                    'local_xy_mm':[v/1e6 for v in pad.GetFPRelativePosition()],
                    'absolute_xy_mm':[v/1e6 for v in pad.GetPosition()]})
    for net, wanted in {'Net-(AE1-A)':{('AE1','1'),('D1','2'),('U2','12')},
                        'Net-(AE2-A)':{('AE2','1'),('D3','2'),('U3','11')}}.items():
        assert members[net] == wanted
    sources = [ROOT/'analysis/v1_1_peer_review_20261014/digital/sources/tmp117.txt',
               ROOT/'analysis/v1_1_peer_review_20261014/sources/rak3172-datasheet.txt',
               ROOT/'analysis/v1_1_release_20261012/identities/review_balance_native.py']
    write('focused-net-check.json', {
        'pcb_sha256':sha(paths['repaired']), 'schematic_sha256':sha(args.scratch/'repaired/stratolink.kicad_sch'),
        'netlist_sha256':sha(xml), 'status':'PASS', 'groups':checked, 'selected_values':expected_values,
        'TMP117_manufacturer_top_view_ball_map':tmp,
        'reference_sources':{str(p.relative_to(ROOT)):sha(p) for p in sources},
        'reference_scope':'Manufacturer TMP117 and standard RAK3172 pin tables plus previously reviewed balancer topology. Full logical equality to the frozen design is independently recorded in repaired-comparison.json.',
        'limits':['DC/native connectivity does not certify I2C rise time, RF impedance/sensitivity or balancer dynamic stability.',
                  'BOOT0 remains hard-strapped to GND through R9=0 ohm; use J20 SWD. J4 UART shares the active GNSS transmitter path.',
                  'U6 exists in the complete schematic/PCB but remains intentionally DNP in the pilot assembly population.'],
    })
    print(json.dumps({'source_scope':'PASS','field_visibility_changes':len(field_changes),
                      'focused_groups':list(checked),'focused_pin_assignments':sum(map(len,checked.values())),
                      'pcb_sha256':sha(paths['repaired'])},indent=2))

if __name__ == '__main__':
    main()
