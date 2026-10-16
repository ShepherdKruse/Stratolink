#!/usr/bin/env python3
"""Read current native snapshots and supplier files; write this audit only.

Run snapshot.py and a native schematic XML export first. This does not refill,
save or edit any KiCad project or supplier package.
"""
import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PACKAGE = ROOT / 'hardware/gerbers/v1.1-pilot-supplier-20261016'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def csvmap(path):
    with path.open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    result = {row['Designator']: row for row in rows}
    assert len(result) == len(rows), 'duplicate references'
    return result


def components(path):
    root = ET.parse(path).getroot()
    return {c.attrib['ref']: {'value': c.findtext('value'),
                            'footprint': c.findtext('footprint'),
                            'fields': {f.attrib['name']: f.text or '' for f in c.findall('fields/field')}}
            for c in root.findall('components/comp')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frozen', type=Path, required=True)
    args = parser.parse_args()
    live = read(HERE / 'live-native.json')
    frozen = read(ROOT / 'analysis/v1_1_engineer_review_20261015/rf-power/native-layout.json')
    live_sch = components(HERE / 'live-netlist.xml')
    frozen_sch = components(PACKAGE / 'native/netlist.xml')
    bom = csvmap(PACKAGE / 'BOM-stratolink.csv')
    cpl = csvmap(PACKAGE / 'CPL-stratolink.csv')
    package = read(PACKAGE / 'assembly-audit.json')
    captured = read(ROOT / 'analysis/v1_1_supplier_review_20261016/bom-final.json')
    assert set(bom) == set(cpl) == set(package['assembly']) and len(bom) == 57
    assert set(package['design_assembly']) - set(bom) == {'U6'}
    assert {'C14', 'C23', 'R27'} <= set(bom)
    excluded = {x['ref'] for x in package['exclusions']}
    assert excluded == {'AE1', 'AE2', 'C5', 'H1', 'H2', 'J1', 'J2', 'J3', 'J4', 'J20', 'U6'}
    assert set(live['footprints']) - set(bom) == excluded

    selected = {}
    for row in captured:
        assert row['checked'] is True
        cells = row['cells']
        ref = (cells[0] or cells[1]).strip()
        assert ref not in selected
        identity = [line.strip() for line in cells[4].splitlines() if line.strip()]
        selected[ref] = {'mpn': identity[0], 'lcsc': identity[1], 'description': ' '.join(identity[2:]),
                         'side': 'top' if cells[0].strip() else 'bottom', 'footprint': cells[3]}
    assert set(selected) == set(bom)
    for ref, row in bom.items():
        for label, src in [('live', live_sch), ('frozen', frozen_sch)]:
            assert src[ref]['fields']['Manufacturer_Part_Number'] == row['Comment'], (label, ref, 'MPN')
            assert src[ref]['fields']['Supplier Part'] == row['LCSC Part #'], (label, ref, 'LCSC')
            assert src[ref]['footprint'] == 'lib:' + row['Footprint'], (label, ref, 'footprint')
        fp = live['footprints'][ref]
        assert fp['fields']['Manufacturer_Part_Number'] == row['Comment']
        assert fp['fields']['Supplier Part'] == row['LCSC Part #']
        assert fp['fp'] == row['Footprint']
        assert selected[ref]['mpn'] == row['Comment'] and selected[ref]['lcsc'] == row['LCSC Part #']
        assert selected[ref]['footprint'] == row['Footprint']
        assert selected[ref]['side'] == cpl[ref]['Layer'] == ('top' if fp['layer'] == 'F.Cu' else 'bottom')
        assert live_sch[ref]['value'] == fp['value'] == frozen_sch[ref]['value']

    padnets = {(p['ref'], p['pin']): p['net'] for p in live['pads']}
    expected = {
        ('U8', '1'): '/SC_BAL_OUT', ('U8', '2'): 'GND', ('U8', '3'): '/SC_HALF_REF',
        ('U8', '4'): '/SC_BAL_OUT', ('U8', '5'): '/VBAT',
        ('R24', '1'): '/VBAT', ('R24', '2'): '/SC_HALF_REF', ('R25', '1'): '/SC_HALF_REF', ('R25', '2'): 'GND',
        ('R26', '1'): '/SC_BAL_OUT', ('R26', '2'): '/SC_MID', ('C22', '1'): '/VBAT', ('C22', '2'): 'GND',
        ('C5', '1'): '/VBAT', ('C5', '2'): 'GND', ('C5', '3'): '/SC_MID',
        ('U1', '2'): '+SOLAR', ('U1', '18'): '/VBAT', ('U1', '19'): 'VSTOR',
        ('U1', '6'): 'VSTOR', ('U1', '3'): 'VSTOR', ('U1', '1'): 'GND',
        ('L1', '1'): 'Net-(U1-LBOOST)', ('L1', '2'): '+SOLAR',
        ('L2', '1'): 'Net-(U1-LBUCK)', ('L2', '2'): '+3.3V',
        ('R1', '1'): 'Net-(U1-VRDIV)', ('R1', '2'): 'Net-(U1-VBAT_OV)',
        ('R2', '1'): 'Net-(U1-VBAT_OV)', ('R2', '2'): 'GND',
    }
    assert all(padnets[k] == v for k, v in expected.items()), 'power pin topology mismatch'
    values = {ref: live['footprints'][ref]['value'] for ref in ['R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'R7', 'R24', 'R25', 'R26', 'C2', 'C3', 'C6', 'C8', 'C21', 'C22', 'C5', 'L1', 'L2']}
    assert values['R1'] == '7.50MΩ' and values['R2'] == '4.22MΩ'
    assert values['R24'] == values['R25'] == '4.75MΩ' and values['R26'] == '22Ω'
    expected_rotations = {'U1': ('bottom', 270), 'U2': ('top', 90), 'U3': ('top', 180),
                          'U4': ('top', 270), 'U5': ('top', 180), 'U7': ('top', 0), 'U8': ('top', 90)}
    for ref, (side, rotation) in expected_rotations.items():
        assert cpl[ref]['Layer'] == side and float(cpl[ref]['Rotation']) == rotation

    groups = collections.defaultdict(list)
    for ref, row in bom.items():
        groups[(row['Comment'], row['LCSC Part #'])].append(ref)
    assert len(groups) == 30
    with (HERE / 'selected-parts.csv').open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['References', 'MPN', 'LCSC', 'Quantity per PCB', 'Schematic values', 'Supplier description'])
        for (mpn, lcsc), refs in sorted(groups.items()):
            writer.writerow([','.join(refs), mpn, lcsc, len(refs), '; '.join(sorted({live_sch[r]['value'] for r in refs})), selected[refs[0]]['description']])

    track_a = {t['uuid']: t for t in frozen['tracks']}
    track_b = {t['uuid']: t for t in live['tracks']}
    delta = {'removed': [track_a[k] for k in sorted(track_a.keys() - track_b.keys())],
             'added': [track_b[k] for k in sorted(track_b.keys() - track_a.keys())],
             'changed': [k for k in sorted(track_a.keys() & track_b.keys()) if track_a[k] != track_b[k]]}
    footprint_changes = {ref: [k for k in ['at', 'angle', 'layer', 'fp', 'value', 'fields'] if live['footprints'][ref][k] != frozen['footprints'][ref][k]] for ref in live['footprints']}
    footprint_changes = {ref: changes for ref, changes in footprint_changes.items() if changes}
    assert not footprint_changes and live['pads'] == frozen['pads']

    sources = {}
    for name in ['stratolink.kicad_pcb', 'stratolink.kicad_sch', 'stratolink.kicad_pro', 'stratolink.kicad_dru']:
        sources['live/' + name] = sha(ROOT / 'hardware/pcb' / name)
        sources['frozen/' + name] = sha(args.frozen / 'hardware/pcb' / name)
    assert sources['live/stratolink.kicad_pcb'] == live['sha256'], 'live source changed after snapshot'
    assert sources['frozen/stratolink.kicad_pcb'] == frozen['sha256']
    result = {
        'source_sha256': sources, 'supplier_package_manifest_sha256': sha(PACKAGE / 'manifest.json'),
        'parts_identity_checks_pass': True, 'assembly_references': len(bom), 'unique_MPN_LCSC_groups': len(groups),
        'sides': dict(collections.Counter(r['Layer'] for r in cpl.values())),
        'sole_automatic_DNP': 'U6', 'retained_UV_support': ['C14', 'C23', 'R27'],
        'manual_or_mechanical_exclusions': sorted(excluded - {'U6'}),
        'all_fitted_live_schematic_PCB_BOM_supplier_MPN_LCSC_footprint_value_side_match': True,
        'power_topology_expected_pairs': len(expected), 'power_values': values,
        'IC_supplier_rotations': {r: {'side': s, 'CPL_degrees': a} for r, (s, a) in expected_rotations.items()},
        'live_vs_frozen': {'footprint_pose_identity_changes': footprint_changes, 'physical_pads_identical': True,
                           'track_delta': delta, 'GND_and_SOLAR_filled_polygons_identical': live['zones'] == frozen['zones'],
                           'copper_graphics_identical': live['graphics'] == frozen['graphics']},
        'limits': ['Matching selected identity is not lot qualification.', 'Pin-net membership is not physical copper continuity.',
                   'Supplier screenshot orientation is recorded separately; this script does not infer orientation from pixels.',
                   'All component ratings and conditional power/RF screens require the accompanying review.'],
    }
    (HERE / 'audit.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ['parts_identity_checks_pass', 'assembly_references', 'unique_MPN_LCSC_groups', 'sides', 'sole_automatic_DNP', 'live_vs_frozen']}, indent=2))


if __name__ == '__main__':
    main()
