"""Compare a local copper cleanup with its baseline using native connectivity."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import pcbnew
import wx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'analysis/v1_1_solar_attachments_20261012/review'))
import check_solar_attachments as audit


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--after', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--allow-copper-polygon', action='append', default=[],
                        help='Exact UUID of an intentionally repaired decorative copper polygon')
    parser.add_argument('--allow-text-conversion', action='append', default=[],
                        help='Exact UUID of copper text retained unchanged on F.Fab after outline conversion')
    args = parser.parse_args()
    app = wx.App(False)
    paths = [args.before, args.after]
    hashes = [sha(p) for p in paths]
    trees = [audit.parse(p.read_text()) for p in paths]
    boards = [pcbnew.LoadBoard(str(p)) for p in paths]
    footprints = [{audit.prop(f, 'Reference'): f for f in audit.nodes(t, 'footprint')} for t in trees]
    assert footprints[0] == footprints[1], 'Footprint geometry or metadata changed'
    invariant_types = ['general', 'setup', 'net', 'gr_line', 'gr_arc', 'gr_rect']
    for kind in invariant_types:
        assert audit.nodes(trees[0], kind) == audit.nodes(trees[1], kind), kind + ' changed'
    old_graphics, new_graphics = [audit.keyed(audit.nodes(t, 'gr_poly')) for t in trees]
    changed_graphics = {uid for uid in old_graphics.keys() | new_graphics.keys()
                        if old_graphics.get(uid) != new_graphics.get(uid)}
    assert changed_graphics == set(args.allow_copper_polygon), ('Unexpected or unused graphic allowance',
        {'unexpected': sorted(changed_graphics - set(args.allow_copper_polygon)),
         'unused': sorted(set(args.allow_copper_polygon) - changed_graphics)})
    for uid in changed_graphics:
        for graphic in (old_graphics.get(uid), new_graphics.get(uid)):
            if graphic is not None:
                assert audit.nodes(graphic, 'layer') in ([['layer', 'F.Cu']], [['layer', 'B.Cu']]), ('Non-copper graphic', uid)
    old_text, new_text = [audit.keyed(audit.nodes(t, 'gr_text')) for t in trees]
    assert old_text.keys() == new_text.keys(), 'Text object added or removed'
    changed_text = {uid for uid in old_text if old_text[uid] != new_text[uid]}
    assert changed_text == set(args.allow_text_conversion), ('Unexpected or unused text conversion', changed_text)
    for uid in changed_text:
        assert audit.nodes(old_text[uid], 'layer') == [['layer', 'F.Cu']]
        assert audit.nodes(new_text[uid], 'layer') == [['layer', 'F.Fab']]
        without_layer = lambda node: [x for x in node if not isinstance(x, list) or x[0] != 'layer']
        assert without_layer(old_text[uid]) == without_layer(new_text[uid]), ('Text content/style/position changed', uid)
    groups = [audit.pad_groups(b) for b in boards]
    assert set(groups[0]) == set(groups[1]), 'Logical pads changed'
    connectivity = [b.GetConnectivity() for b in boards]
    physical_pads = 0
    for key in groups[0]:
        old_pads = {p.m_Uuid.AsString(): p for p in groups[0][key]}
        new_pads = {p.m_Uuid.AsString(): p for p in groups[1][key]}
        assert set(old_pads) == set(new_pads), ('Physical pads changed', key)
        for uid, pad in new_pads.items():
            assert pad.GetNetname() == old_pads[uid].GetNetname(), ('Net changed', key)
            assert audit.connected_keys(connectivity[0], old_pads[uid]) == audit.connected_keys(connectivity[1], pad), ('Connectivity changed', key)
            physical_pads += 1
    opens = [c.GetUnconnectedCount(False) for c in connectivity]
    assert opens == [0, 0], ('Unconnected items', opens)
    delta = {}
    for kind in ['segment', 'arc', 'via', 'zone']:
        old, new = [audit.keyed(audit.nodes(t, kind)) for t in trees]
        delta[kind] = {'removed': sorted(old.keys() - new.keys()), 'added': sorted(new.keys() - old.keys()), 'changed': sorted(k for k in old.keys() & new.keys() if old[k] != new[k])}
    assert hashes == [sha(p) for p in paths], 'Read-only check modified input'
    report = {'before_sha256': hashes[0], 'after_sha256': hashes[1], 'footprints_unchanged': len(footprints[0]), 'physical_pads_checked': physical_pads, 'logical_pads_checked': len(groups[0]), 'native_opens': opens, 'invariant_types': invariant_types, 'allowed_copper_polygon_changes': sorted(changed_graphics), 'text_retained_on_fab_layer': sorted(changed_text), 'delta': delta}
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'delta'}, indent=2))


if __name__ == '__main__':
    main()
