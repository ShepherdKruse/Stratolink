#!/usr/bin/env python3
"""Verify only the declared label translations, guard polygon and stitch in a trial."""
from pathlib import Path
import argparse, copy, hashlib, json, sys
import pcbnew, wx
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'analysis/v1_1_solar_attachments_20261012/review'))
import check_solar_attachments as a


def equal(x, y):
    if isinstance(x, list) or isinstance(y, list):
        return isinstance(x, list) and isinstance(y, list) and len(x) == len(y) and all(equal(i, j) for i, j in zip(x, y))
    if x == y:
        return True
    try:
        return abs(float(x)-float(y)) <= .0000011
    except (ValueError, TypeError):
        return False


def translated(tree, delta):
    out = copy.deepcopy(tree)
    def move(node):
        if not isinstance(node, list) or not node:
            return
        if node[0] in ['xy', 'at', 'start', 'end', 'mid', 'center']:
            node[1], node[2] = str(float(node[1])+delta[0]), str(float(node[2])+delta[1])
        else:
            for child in node:
                move(child)
    move(out)
    return out


def check(before, after, plan_path):
    raw = [p.read_bytes() for p in [before, after]]
    old, new = [a.parse(x.decode()) for x in raw]
    plan = json.loads(plan_path.read_text())
    assert hashlib.sha256(raw[0]).hexdigest() == plan['source_sha256']
    for kind in ['footprint', 'general', 'setup', 'net', 'segment', 'arc', 'group', 'gr_line', 'gr_arc', 'gr_rect']:
        assert a.nodes(old, kind) == a.nodes(new, kind), ('Unexpected guard scope change', kind)
    groups = {g[1]: g for g in a.nodes(old, 'group')}
    moved = {}
    for name, delta in plan['moves'].items():
        for uid in a.nodes(groups[name], 'members')[0][1:]:
            assert uid not in moved
            moved[uid] = delta
    draws = [a.keyed([x for kind in ['gr_poly', 'gr_text'] for x in a.nodes(t, kind)]) for t in [old, new]]
    assert not draws[0].keys()-draws[1].keys()
    for uid in draws[0]:
        expected = translated(draws[0][uid], moved[uid]) if uid in moved else draws[0][uid]
        assert equal(expected, draws[1][uid]), ('Unexpected drawing change', uid)
    assert set(moved) <= draws[0].keys()
    added = draws[1].keys()-draws[0].keys()
    assert added == {'f5107420-9f61-54b6-889e-abad2b9900fe'}
    shape = draws[1][next(iter(added))]
    assert a.field(shape, 'net') == 'GND' and a.field(shape, 'layer') == 'F.Cu'
    actual_points = [p[1:] for p in a.nodes(shape, 'pts')[0][1:]]
    assert equal(actual_points, plan['guard']), 'Guard polygon differs from exact plan'
    old_vias, new_vias = [a.keyed(a.nodes(t, 'via')) for t in [old, new]]
    assert all(old_vias[u] == new_vias[u] for u in old_vias)
    assert new_vias.keys()-old_vias.keys() == {'cb09c440-db10-5717-8a62-d14623df26b2'}
    old_zones, new_zones = [a.keyed(a.nodes(t, 'zone')) for t in [old, new]]
    assert old_zones.keys() == new_zones.keys()
    for uid in old_zones:
        stripped = [[x for x in z[uid] if not (isinstance(x, list) and x and x[0] == 'filled_polygon')] for z in [old_zones, new_zones]]
        assert stripped[0] == stripped[1], ('Changed zone outline/rules', uid)
    board = pcbnew.LoadBoard(str(after))
    via = next(v for v in board.GetTracks() if v.m_Uuid.AsString() == 'cb09c440-db10-5717-8a62-d14623df26b2')
    assert via.GetNetname() == 'GND' and via.GetWidth(pcbnew.F_Cu) == 500000 and via.GetDrillValue() == 300000
    assert [via.GetPosition().x/1e6, via.GetPosition().y/1e6] == plan['via']
    assert not via.IsOnLayer(pcbnew.F_Mask) and not via.IsOnLayer(pcbnew.B_Mask)
    assert raw == [p.read_bytes() for p in [before, after]]
    return {'before_sha256': hashlib.sha256(raw[0]).hexdigest(), 'after_sha256': hashlib.sha256(raw[1]).hexdigest(),
            'plan_sha256': hashlib.sha256(plan_path.read_bytes()).hexdigest(), 'exact_group_moves_mm': plan['moves'],
            'rigidly_translated_graphics': len(moved), 'all_other_original_graphics_unchanged': True,
            'only_added_geometry': ['Exact planned F.Cu GND guard polygon', '0.5/0.3 mm GND stitch at [55.45,46.65]'],
            'stitch_has_no_front_or_back_mask_aperture_by_native_layer_flags': True,
            'original_tracks_pads_footprints_and_zone_definitions_unchanged': True, 'source_bytes_unchanged': True}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--before', type=Path, required=True)
    p.add_argument('--after', type=Path, required=True)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    app = wx.App(False)
    result = check(args.before, args.after, args.plan)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
