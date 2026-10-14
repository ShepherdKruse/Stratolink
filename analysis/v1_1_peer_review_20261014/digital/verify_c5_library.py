#!/usr/bin/env python3
"""Read-only exact C5 library delta and placed courtyard agreement review."""
from pathlib import Path
import argparse, copy, hashlib, json, sys
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'analysis/v1_1_solar_attachments_20261012/review'))
import check_solar_attachments as a

IDS = {'2136d50d-e38e-4c1c-bb15-8bc93ba83913', '30d45e65-08b6-45f7-8c67-3e8daa682804',
       'e71d0a9b-bf77-4095-a17e-5c02fbc85554', 'b5d37c5e-1865-474d-9ef2-acca1de6a446'}
ASSEMBLY = 'Preserve proven outer polarity. Center pad 3 connects to SC_MID through R26 and the active balancer. Hand-install after board cleaning; no normal reflow.'


def courtyard(tree, layer):
    result = a.keyed([node for node in a.nodes(tree, 'fp_line') if a.field(node, 'layer') == layer])
    assert set(result) == IDS
    return result


def without_approved(tree):
    result = copy.deepcopy(tree)
    result[:] = [x for x in result if not (isinstance(x, list) and x and a.field(x, 'uuid') in IDS)]
    for prop in a.nodes(result, 'property'):
        if prop[1] in ['Description', 'Assembly_Note']:
            prop[2] = '<exact reviewed text>'
    return result


def check(pcb, before, after):
    raw = [p.read_bytes() for p in [pcb, before, after]]
    board, old, new = [a.parse(x.decode()) for x in raw]
    fp = next(f for f in a.nodes(board, 'footprint') if a.prop(f, 'Reference') == 'C5')
    assert a.field(fp, 'layer') == 'B.Cu' and a.field(new, 'layer') == 'F.Cu'
    assert without_approved(old) == without_approved(new), 'Unapproved C5 library edit'
    text = {}
    for name in ['Assembly_Note', 'Description']:
        assert a.prop(new, name) == a.prop(fp, name), ('Library/placed text mismatch', name)
        text[name] = {'before': a.prop(old, name), 'after': a.prop(new, name)}
    assert text['Assembly_Note']['after'] == ASSEMBLY
    library, placed = courtyard(new, 'F.CrtYd'), courtyard(fp, 'B.CrtYd')
    for uid, original in library.items():
        mirrored = copy.deepcopy(original)
        for name in ['start', 'end']:
            node = a.nodes(mirrored, name)[0]
            node[2] = format(-float(node[2]), '.10g')
        a.nodes(mirrored, 'layer')[0][1] = 'B.CrtYd'
        assert mirrored == placed[uid], ('Placed/library courtyard mismatch', uid)
    points = [node[1:] for shape in library.values() for kind in ['start', 'end'] for node in a.nodes(shape, kind)]
    bounds = [min(float(p[n]) for p in points) for n in [0, 1]] + [max(float(p[n]) for p in points) for n in [0, 1]]
    assert bounds == [-7.375, -20.375, 7.375, 15.375], bounds
    assert raw == [p.read_bytes() for p in [pcb, before, after]]
    return {'pcb_sha256': hashlib.sha256(raw[0]).hexdigest(), 'before_library_sha256': hashlib.sha256(raw[1]).hexdigest(),
            'after_library_sha256': hashlib.sha256(raw[2]).hexdigest(), 'exact_text_updates': text,
            'only_other_library_changes': 'Four original courtyard line geometries; all other source nodes identical',
            'courtyard_uuids': sorted(IDS), 'library_courtyard_bounds_mm': bounds,
            'board_courtyard_matches_y_mirrored_library': True, 'source_bytes_unchanged': True,
            'limit': 'The 0.125 mm courtyard allowance around the maximum case/terminal envelope is an assembly envelope, not qualification of hand placement, soldering, flight flex or manufacturer tolerance.'}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pcb', type=Path, required=True)
    p.add_argument('--before-library', type=Path, required=True)
    p.add_argument('--after-library', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    result = check(args.pcb, args.before_library, args.after_library)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
