#!/usr/bin/env python3
"""Merge a hash-pinned power review into a fresh copy of the integrated board."""
from pathlib import Path
import argparse
import copy
import importlib.util
import json
import shutil
import subprocess
import uuid
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('merge', HERE / 'merge_reviews.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
h, cad, edit = m.h, m.cad, m.edit
NEW = {'U8', 'R24', 'R25', 'R26', 'C22'}
OLD_VBAT, VBAT = 'Net-(U1-VBAT)', '/VBAT'
EXPECTED_NEW_NETS = {
    'U8': {'1': '/SC_BAL_OUT', '2': 'GND', '3': '/SC_HALF_REF', '4': '/SC_BAL_OUT', '5': VBAT},
    'R24': {'1': VBAT, '2': '/SC_HALF_REF'},
    'R25': {'1': '/SC_HALF_REF', '2': 'GND'},
    'R26': {'1': '/SC_BAL_OUT', '2': '/SC_MID'},
    'C22': {'1': VBAT, '2': 'GND'},
}


def direct(text, kind):
    result = []
    for start, end, depth in edit.spans(text):
        if depth == 1:
            node = cad.parse(text[start:end])
            if node[0] == kind:
                result.append((start, end, text[start:end], node))
    return result


def checked_nodes(text, kind):
    result = h.nodes(text, kind)
    assert len(result) == len(direct(text, kind)), ('Duplicate reference/UUID', kind)
    return result


def rename_storage_net(text, already_renamed=False):
    """Change net nodes only, never descriptions, pin functions or other strings."""
    changes, old_count, new_count = [], 0, 0
    for start, end, depth in edit.spans(text):
        node = cad.parse(text[start:end])
        if node and node[0] == 'net':
            assert len(node) == 2, 'Expected KiCad 10 named-net representation'
            if node[1] == OLD_VBAT:
                changes.append((start, end, '(net ' + json.dumps(VBAT) + ')'))
                old_count += 1
            elif node[1] == VBAT:
                new_count += 1
    assert old_count == text.count(json.dumps(OLD_VBAT)), 'Storage-net name occurs outside net nodes'
    if already_renamed:
        assert not old_count and new_count, 'Reviewed power board must already use /VBAT'
    else:
        assert old_count and not new_count, 'Storage rename would merge nets or has already run'
    return edit.replace(text, changes)


def without(node, kinds):
    return [x for x in node if not (isinstance(x, list) and x and x[0] in kinds)]


def validate_thermal_manifest(manifest):
    assert set(manifest) == {'pcb_sha256', 'changes'}, 'Unexpected thermal manifest fields'
    assert len(manifest['changes']) == 2
    assert {c['reference'] for c in manifest['changes']} == {'D3', 'J4'}
    for change in manifest['changes']:
        assert set(change) == {'reference', 'pad', 'pad_uuid', 'before', 'after'}
        assert change['pad'] == '1' and str(uuid.UUID(change['pad_uuid'])) == change['pad_uuid']
        assert change['before'] == {'thermal_gap': None, 'thermal_bridge_width': None}
        assert change['after'] == {'thermal_gap': 0.25, 'thermal_bridge_width': 0.25}


def thermal_pad_delta(before, reviewed, target, change):
    """Validate just the reviewed thermal attributes; retain the target pad geometry."""
    pad_map = lambda fp: {p[3][1]: p for p in direct(fp, 'pad')}
    old, new, current = [pad_map(fp)['1'] for fp in (before, reviewed, target)]
    for pad in (old, new, current):
        assert cad.scalar(pad[3], 'uuid') == change['pad_uuid']
    for pad, expected in ((old, change['before']), (new, change['after']), (current, change['before'])):
        actual = {key: float(cad.scalar(pad[3], key)) if cad.one(pad[3], key) else None for key in expected}
        assert actual == expected, ('Unexpected pad thermal state', change['reference'], actual)
    assert without(old[3], set(change['after'])) == without(new[3], set(change['after'])), 'Thermal review also changed pad geometry'
    patched = current[2].rstrip()[:-1] + ' ' + ' '.join('(%s %s)' % (k, v) for k, v in change['after'].items()) + ')'
    return edit.replace(target, [(current[0], current[1], patched)])


def pin_definitions(schematic, instance):
    libs = {n[3][1]: n[3] for n in direct(direct(schematic, 'lib_symbols')[0][2], 'symbol')}
    symbol = libs[cad.scalar(instance, 'lib_id')]
    pins = [pin for unit in cad.nodes(symbol, 'symbol') for pin in cad.nodes(unit, 'pin')]
    result = {cad.scalar(pin, 'number'): pin for pin in pins}
    assert len(result) == len(pins), 'Duplicate embedded pin definitions require review'
    return result


def sync_pad_metadata(block, pins):
    changes = []
    for start, end, original, node in direct(block, 'pad'):
        assert node[1] in pins
        pin = pins[node[1]]
        fields = {'pintype': pin[1]}
        if cad.scalar(pin, 'name') not in ('', '~', None):
            fields['pinfunction'] = cad.scalar(pin, 'name')
        remove = [(s, e, '') for s, e, b, n in direct(original, 'pinfunction') + direct(original, 'pintype')]
        new = edit.replace(original, remove).rstrip()[:-1]
        new += ' ' + ' '.join('(%s %s)' % (k, json.dumps(v)) for k, v in fields.items()) + ')'
        changes.append((start, end, new))
    return edit.replace(block, changes)


def export_netmap(schematic, output):
    result = subprocess.run([h.CLI, 'sch', 'export', 'netlist', '--format', 'kicadxml',
                             '--output', str(output), str(schematic)], capture_output=True, text=True, check=True)
    output.with_suffix('.log').write_text(result.stdout + result.stderr)
    netmap = {}
    for net in ET.parse(output).findall('.//nets/net'):
        for node in net.findall('node'):
            key = (node.get('ref'), node.get('pin'))
            if key[0].startswith('#'):
                continue
            assert key not in netmap
            netmap[key] = net.get('name')
    return netmap


def properties(block, values, pcb=False):
    current = {x[3][1]: x for x in direct(block, 'property')}
    assert len(current) == len(direct(block, 'property'))
    changes, added = [], []
    ref = cad.prop(cad.parse(block), 'Reference')
    for key, value in values.items():
        if key in current:
            start, end, original, node = current[key]
            prefix = '(property ' + json.dumps(key)
            new = original.replace(prefix + ' ' + json.dumps(node[2], ensure_ascii=False),
                                   prefix + ' ' + json.dumps(value, ensure_ascii=False), 1)
            assert new != original or node[2] == value, (ref, key)
            changes.append((start, end, new))
        else:
            identity = str(uuid.uuid5(uuid.NAMESPACE_URL, 'stratolink-release-field/' + ref + '/' + key))
            layer = '(layer "B.Fab") (uuid "%s")' % identity if pcb else ''
            added.append('(property %s %s (at 0 0 0) %s (effects (font (size 1 1)) (hide yes)))' %
                         (json.dumps(key), json.dumps(value, ensure_ascii=False), layer))
    block = edit.replace(block, changes)
    return block.rstrip()[:-1] + '\n' + '\n'.join(added) + '\n)'


R1_FIELDS = {
    'Value': '7.50MΩ', 'Description': 'FRC0402F7504TS; 7.50 MΩ, 1%, 100 ppm/°C charge-ceiling resistor',
    'Datasheet': 'https://www.lcsc.com/product-detail/C3013187.html',
    'Manufacturer': 'FOJAN', 'Manufacturer_Part_Number': 'FRC0402F7504TS',
    'Supplier': 'LCSC', 'LCSC': 'C3013187', 'Supplier Part': 'C3013187',
    'MPN': 'FRC0402F7504TS', 'LCSC Part #': 'C3013187',
}
C5_FIELDS = {
    'Description': 'DMF4B5R5G105M3DTA0; 1 F dual-cell capacitor, pad 1 positive, pad 2 negative, pad 3 midpoint; hand-install after reflow and cleaning',
    'Assembly_Note': 'Preserve proven outer polarity. Center pad 3 connects to SC_MID through R26 and the active balancer. Hand-install after board cleaning; no normal reflow.',
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--reviewed', type=Path, required=True)
    parser.add_argument('--pcb-sha256', required=True)
    parser.add_argument('--sch-sha256', required=True)
    parser.add_argument('--thermal-manifest', type=Path,
                        help='Author manifest permitting only D3.1/J4.1 scoped thermal overrides')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source, reviewed, out = [p.resolve() for p in (args.source, args.reviewed, args.output)]
    assert not out.exists() and source not in out.parents and reviewed not in out.parents
    assert out.is_relative_to(h.SCRATCH)
    assert h.sha(reviewed / 'stratolink.kicad_pcb') == args.pcb_sha256
    assert h.sha(reviewed / 'stratolink.kicad_sch') == args.sch_sha256
    thermals = {}
    if args.thermal_manifest:
        manifest = json.loads(args.thermal_manifest.read_text())
        validate_thermal_manifest(manifest)
        assert manifest['pcb_sha256'] == args.pcb_sha256
        thermals = {c['reference']: c for c in manifest['changes']}
    protected = {str(p): h.sha(p) for folder in (source, reviewed) for p in folder.rglob('*') if p.is_file()}
    shutil.copytree(source, out)
    baseline = h.SCRATCH / 'baseline'
    for name in ('stratolink.kicad_pcb', 'stratolink.kicad_sch'):
        expected = subprocess.check_output(['git', 'show', '5997979:hardware/pcb/' + name], cwd=h.ROOT)
        assert (baseline / name).read_bytes() == expected, ('Power merge baseline drift', name)
        protected[str(baseline / name)] = h.sha(baseline / name)
    report = dict(source=str(source), reviewed=str(reviewed), candidate=str(out), inputs=protected)
    if thermals:
        protected[str(args.thermal_manifest.resolve())] = h.sha(args.thermal_manifest)
        report['reviewed_thermal_changes'] = manifest
    audit = out / 'power-merge-audit'
    audit.mkdir()
    source_nets = export_netmap(source / 'stratolink.kicad_sch', audit / 'source-netlist.xml')
    power_sch = (reviewed / 'stratolink.kicad_sch').read_text()
    power_symbols = checked_nodes(power_sch, 'symbol')

    # Rename only the already-established storage net before the three-way merge.
    # This prevents a net-name change from masquerading as a track reroute.
    pcb = out / 'stratolink.kicad_pcb'
    base = rename_storage_net((baseline / pcb.name).read_text())
    power = rename_storage_net((reviewed / pcb.name).read_text(), already_renamed=True)
    text = rename_storage_net((out / pcb.name).read_text())
    assert without(cad.parse(base), {'footprint', 'segment', 'via', 'zone'}) == without(cad.parse(power), {'footprint', 'segment', 'via', 'zone'}), 'Unsupported power-board global/outline/drawing change'
    for kind in ('footprint', 'segment', 'via', 'zone'):
        for content in (base, power, text):
            checked_nodes(content, kind)
    text, report['routing_delta'] = m.merge_objects(text, base, power, ['segment', 'via', 'zone'])
    target_fp, base_fp, power_fp = [checked_nodes(t, 'footprint') for t in (text, base, power)]
    assert power_fp.keys() - base_fp.keys() == NEW and base_fp.keys() <= power_fp.keys()
    # This merger intentionally retains existing placement and footprint identity.
    # Reject a reviewed relocation/rotation/pad change instead of silently dropping it.
    for ref in base_fp:
        before_node, after_node = base_fp[ref][3], power_fp[ref][3]
        if ref in thermals:
            thermal_pad_delta(base_fp[ref][2], power_fp[ref][2], target_fp[ref][2], thermals[ref])
            # Strip the two approved attributes from the reviewed copy only for
            # the broad preservation assertion below. No other delta is ignored.
            after_node = copy.deepcopy(after_node)
            for index, child in enumerate(after_node):
                if isinstance(child, list) and child[:2] == ['pad', '1']:
                    after_node[index] = without(child, set(thermals[ref]['after']))
        ignored = {'property', 'pad'} if ref == 'C5' else {'property'}
        assert without(before_node, ignored) == without(after_node, ignored), ('Unsupported existing footprint geometry change', ref)
        if ref not in ('R1', 'C5'):
            assert m.footprint_signature(before_node)[1] == m.footprint_signature(after_node)[1], ('Unsupported existing footprint field change', ref)
    for ref in NEW:
        fp, sym = power_fp[ref][3], power_symbols[ref][3]
        padnets = {p[3][1]: cad.scalar(p[3], 'net') for p in direct(power_fp[ref][2], 'pad')}
        assert len(padnets) == len(direct(power_fp[ref][2], 'pad')) and padnets == EXPECTED_NEW_NETS[ref], ('Balancer pad topology', ref, padnets)
        for field in ('Value', 'Supplier Part', 'Manufacturer_Part_Number'):
            assert cad.prop(fp, field) and cad.prop(fp, field) == cad.prop(sym, field), ('PCB/schematic field mismatch', ref, field)
    assert all(cad.prop(power_fp['R1'][3], k) == R1_FIELDS[k] and cad.prop(power_symbols['R1'][3], k) == R1_FIELDS[k]
               for k in ('Value', 'Supplier Part', 'Manufacturer_Part_Number')), 'R1 reviewed selection differs from merge selection'
    changes = []
    for ref, change in thermals.items():
        fp = target_fp[ref]
        patched = thermal_pad_delta(base_fp[ref][2], power_fp[ref][2], fp[2], change)
        changes.append((fp[0], fp[1], patched))
    r1 = target_fp['R1']
    changes.append((r1[0], r1[1], properties(r1[2], R1_FIELDS, pcb=True)))
    cap = target_fp['C5']
    cap_block = cap[2]
    pads = {n[3][1]: n for n in direct(cap_block, 'pad')}
    before, after = pads['3'], next(n for n in direct(power_fp['C5'][2], 'pad') if n[3][1] == '3')
    strip_net = lambda n: [x for x in n if not (isinstance(x, list) and x and x[0] in {'net', 'pinfunction', 'pintype'})]
    base_pads = {p[3][1]: p[3] for p in direct(base_fp['C5'][2], 'pad')}
    power_pads = {p[3][1]: p[3] for p in direct(power_fp['C5'][2], 'pad')}
    assert base_pads.keys() == power_pads.keys() == pads.keys() == {'1', '2', '3'}
    for number in base_pads:
        assert strip_net(base_pads[number]) == strip_net(power_pads[number]), ('Capacitor pad geometry changed', number)
    assert {n: cad.scalar(power_pads[n], 'net') for n in power_pads} == {'1': VBAT, '2': 'GND', '3': '/SC_MID'}, 'Capacitor polarity/midpoint changed'
    assert cad.scalar(pads['1'][3], 'net') == VBAT and cad.scalar(pads['2'][3], 'net') == 'GND'
    assert strip_net(before[3]) == strip_net(after[3]), 'Capacitor midpoint pad geometry changed'
    assert not cad.one(before[3], 'net') and cad.scalar(after[3], 'net') == '/SC_MID'
    cap_block = edit.replace(cap_block, [(before[0], before[1], after[2])])
    cap_pins = pin_definitions(power_sch, power_symbols['C5'][3])
    assert {n: (p[1], cad.scalar(p, 'name')) for n, p in cap_pins.items()} == {'1': ('passive', '+'), '2': ('passive', '-'), '3': ('passive', 'MID')}
    cap_block = sync_pad_metadata(cap_block, cap_pins)
    changes.append((cap[0], cap[1], properties(cap_block, C5_FIELDS, pcb=True)))
    additions = [sync_pad_metadata(power_fp[r][2], pin_definitions(power_sch, power_symbols[r][3])) for r in sorted(NEW)]
    text = edit.replace(text, changes).rstrip()[:-1] + '\n' + '\n'.join(additions) + '\n)\n'
    stale = [(s, e, '') for s, e, d in edit.spans(text) if d == 2 and text[s:e].startswith(('(filled_polygon', '(filled_areas_thickness'))]
    pcb.write_text(edit.replace(text, stale))

    sch = out / 'stratolink.kicad_sch'
    base, power, text = [(folder / sch.name).read_text() for folder in (baseline, reviewed, out)]
    original_instances, power_instances, target_instances = [checked_nodes(t, 'symbol') for t in (base, power, text)]
    assert power_instances.keys() - original_instances.keys() == NEW
    assert original_instances.keys() <= power_instances.keys()
    schematic_kinds = {'symbol', 'lib_symbols', 'paper', 'wire', 'junction', 'label', 'text', 'no_connect'}
    assert without(cad.parse(base), schematic_kinds) == without(cad.parse(power), schematic_kinds), 'Unsupported schematic-level change'
    for ref, original in original_instances.items():
        before_node, after_node = original[3], power_instances[ref][3]
        if ref not in ('R1', 'C5'):
            assert before_node == after_node, ('Unsupported existing symbol change', ref)
        elif ref == 'R1':
            assert without(before_node, {'property'}) == without(after_node, {'property'}), 'R1 existing symbol moved or remapped'
        else:
            assert without(before_node, {'property', 'lib_id', 'pin'}) == without(after_node, {'property', 'lib_id', 'pin'}), 'C5 instance moved or remapped'
            assert without(before_node, {'property'}) == without(target_instances[ref][3], {'property'}), 'Target C5 has conflicting symbol changes'
            oldpins = {p[1]: p for p in cad.nodes(before_node, 'pin')}
            newpins = {p[1]: p for p in cad.nodes(after_node, 'pin')}
            assert oldpins.keys() == {'1', '2'} and newpins.keys() == {'1', '2', '3'}
            assert all(newpins[n] == oldpins[n] for n in oldpins), 'C5 original pin identities changed'
            olddefs, newdefs = pin_definitions(base, before_node), pin_definitions(power, after_node)
            assert all(cad.one(olddefs[n], 'at') == cad.one(newdefs[n], 'at') for n in olddefs), 'C5 outer symbol connection points changed'
    changes = []
    r1 = target_instances['R1']
    changes.append((r1[0], r1[1], properties(r1[2], R1_FIELDS)))
    cap = target_instances['C5']
    cap_block = m.preserve_properties(power_instances['C5'][2], cap[2])
    changes.append((cap[0], cap[1], properties(cap_block, C5_FIELDS)))
    paper_old, paper_new = direct(text, 'paper')[0], direct(power, 'paper')[0]
    changes.append((paper_old[0], paper_old[1], paper_new[2]))
    libs_old, libs_base, libs_power = [direct(t, 'lib_symbols')[0] for t in (text, base, power)]
    lib_map = lambda block: {n[3][1]: n for n in direct(block, 'symbol')}
    oldlibs, baselibs, powerlibs = [lib_map(n[2]) for n in (libs_old, libs_base, libs_power)]
    assert baselibs.keys() <= powerlibs.keys()
    assert all(baselibs[k][3] == powerlibs[k][3] for k in baselibs), 'Reviewed power candidate refreshed an existing embedded symbol'
    addedlibs = powerlibs.keys() - baselibs.keys()
    assert addedlibs == {'Stratolink_Power:TLV8801DBVT', 'Stratolink_Power:DMF4B5R5G105M3DTA0_3T'}
    assert not addedlibs & oldlibs.keys()
    libs = libs_old[2].rstrip()[:-1] + '\n' + '\n'.join(powerlibs[k][2] for k in sorted(addedlibs)) + '\n)'
    changes.append((libs_old[0], libs_old[1], libs))
    text = edit.replace(text, changes).rstrip()[:-1] + '\n' + '\n'.join(power_instances[r][2] for r in sorted(NEW)) + '\n)\n'
    for kind in ('wire', 'junction', 'label', 'text', 'no_connect'):
        for content in (base, power, text):
            checked_nodes(content, kind)
    text, report['schematic_delta'] = m.merge_objects(text, base, power, ['wire', 'junction', 'label', 'text', 'no_connect'])
    sch.write_text(text)
    libfile = 'Stratolink_Power.kicad_sym'
    shutil.copyfile(reviewed / 'lib' / libfile, out / 'lib' / libfile)
    table = out / 'sym-lib-table'
    power_entry = next(x for x in direct((reviewed / table.name).read_text(), 'lib') if cad.scalar(x[3], 'name') == 'Stratolink_Power')
    assert not any(cad.scalar(x[3], 'name') == 'Stratolink_Power' for x in direct(table.read_text(), 'lib'))
    table.write_text(table.read_text().rstrip()[:-1] + '\n' + power_entry[2] + '\n)\n')
    merged_nets = export_netmap(sch, audit / 'merged-netlist.xml')
    expected_nets = {key: VBAT if value == OLD_VBAT else value for key, value in source_nets.items()}
    for ref, pins in EXPECTED_NEW_NETS.items():
        for number, net in pins.items():
            assert (ref, number) not in expected_nets
            expected_nets[(ref, number)] = net
    assert ('C5', '3') not in expected_nets
    expected_nets[('C5', '3')] = '/SC_MID'
    assert merged_nets == expected_nets, ('Unexpected merged physical net membership', sorted(set(merged_nets.items()) ^ set(expected_nets.items())))
    report['native_netlist_verification'] = dict(before_pin_count=len(source_nets), after_pin_count=len(merged_nets),
        retained_all_existing_connections=True, only_existing_net_rename=[OLD_VBAT, VBAT],
        new_parts=sorted(NEW), existing_pad_newly_connected='C5.3 /SC_MID',
        feedback='U8.1 OUT and U8.4 -IN share SC_BAL_OUT before R26; C5.3 connects after R26')
    assert all(h.sha(Path(p)) == v for p, v in protected.items()), 'Input changed during integration'
    report['files'] = {str(p.relative_to(out)): h.sha(p) for p in out.rglob('*') if p.is_file()}
    (out / 'power-merge.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in {'inputs', 'files'}}, indent=2))


if __name__ == '__main__':
    main()
