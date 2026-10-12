#!/usr/bin/env python3
"""Compare current report to the frozen v1.1 TMP117 baseline; no CAD edits."""
from collections import Counter
from pathlib import Path
import json
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


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
    return root


def by_uuid(tree):
    result = {}
    def visit(item):
        for child in item:
            if isinstance(child, list):
                if child[0] == 'uuid':
                    result[child[1]] = item
                visit(child)
    visit(tree)
    return result


def signature(item):
    return json.dumps({
        'type': item['type'], 'severity': item['severity'],
        'description': item['description'],
        'item_uuids': sorted(x['uuid'] for x in item.get('items', [])),
    }, sort_keys=True)


def delta(before_path, after_path):
    before, after = (json.loads(p.read_text()) for p in [before_path, after_path])
    sections = {}
    for category in ['violations', 'schematic_parity', 'unconnected_items']:
        old = Counter(signature(x) for x in before[category])
        new = Counter(signature(x) for x in after[category])
        sections[category] = {
            'before_count': sum(old.values()), 'after_count': sum(new.values()),
            'added': [json.loads(k) for k in (new-old).elements()],
            'removed': [json.loads(k) for k in (old-new).elements()],
        }
    return {'before_report': str(before_path.relative_to(ROOT)),
            'after_report': str(after_path.relative_to(ROOT)), 'sections': sections}


def main():
    result = {
        'project_rules': delta(
            ROOT/'analysis/v1_1_implementation_20261012/promotion/drc-project.json',
            HERE.parent/'drc-project.json'),
        'enabled_0p15mm_screen': delta(
            HERE/'clearance_screen/before/drc.json', HERE/'clearance_screen/after/drc.json'),
    }
    erc_paths = [ROOT/'analysis/v1_1_implementation_20261012/promotion/erc-project.json',
                 HERE.parent/'erc-project.json']
    erc = [Counter(signature(v) for sheet in json.loads(p.read_text())['sheets']
                   for v in sheet['violations']) for p in erc_paths]
    result['erc'] = {'sections': {'violations': {
        'before_count': sum(erc[0].values()), 'after_count': sum(erc[1].values()),
        'added': [json.loads(k) for k in (erc[1]-erc[0]).elements()],
        'removed': [json.loads(k) for k in (erc[0]-erc[1]).elements()],
    }}}
    # KiCad can choose a different representative collision/pin pair after
    # other objects disappear. Preserve raw differences and explain only the
    # independently verified, unchanged cases; never silently discard them.
    old_objects = by_uuid(parse((HERE/'baseline/stratolink.kicad_pcb').read_text()))
    new_objects = by_uuid(parse((ROOT/'hardware/pcb/stratolink.kicad_pcb').read_text()))
    for finding in result['enabled_0p15mm_screen']['sections']['violations']['added']:
        if finding['type'] == 'clearance' and all(
                u in old_objects and old_objects[u] == new_objects.get(u)
                for u in finding['item_uuids']):
            finding['classification'] = 'preexisting_geometry_reported_with_different_pair'
            finding['reason'] = 'Both complete copper objects are identical in baseline and final CAD.'
    import xml.etree.ElementTree as ET
    def net_map(path):
        return {(n.get('ref'), n.get('pin')): net.get('name')
                for net in ET.parse(path).findall('.//nets/net') for n in net.findall('node')}
    old_nets, new_nets = net_map(HERE/'baseline/netlist.xml'), net_map(HERE/'netlist.xml')
    for finding in result['erc']['sections']['violations']['added']:
        if (finding['type'] == 'pin_to_pin'
                and set(finding['item_uuids']) == {
                    '97fe1358-9111-4cae-ace0-69f4a04c9922',
                    '09be2ffb-a532-464a-b735-3417496a13de'}
                and all(old_nets.get(k) == new_nets.get(k) == 'GND'
                        for k in [('U6', '5'), ('C14', '1')])):
            finding['classification'] = 'preexisting_ground_net_warning_new_representative'
            finding['reason'] = 'U6.5 and C14.1 were already on GND; removed #PWR034 was the previous comparison endpoint.'
    result['status'] = 'pass' if all(
        all(x.get('classification', '').startswith('preexisting_') for x in category['added'])
        for report in result.values() for category in report['sections'].values()) else 'fail'
    (HERE/'drc-comparison.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))
    assert result['status'] == 'pass', 'New DRC, parity or connectivity finding'


if __name__ == '__main__':
    main()
