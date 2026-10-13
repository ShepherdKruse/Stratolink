#!/usr/bin/env python3
"""Freeze the five added balancer footprints without changing physical CAD.

Run with KiCad's bundled Python. Input is never written; output must be fresh
release scratch. Optionally re-freeze the two explicitly reviewed thermal pads.
"""
from pathlib import Path
import argparse
import copy
import hashlib
import importlib.util
import json
import shutil

import pcbnew
import wx

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('power_merge', HERE.parent / 'merge_power.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
h, cad, edit = m.h, m.cad, m.edit
NEW = {'U8', 'R24', 'R25', 'R26', 'C22'}


def digest(node):
    return hashlib.sha256(json.dumps(node, ensure_ascii=False).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--thermal-manifest', type=Path,
                        help='Exact reviewed D3.1/J4.1 changes already applied by merge_power')
    args = parser.parse_args()
    source, out = args.candidate.resolve(), args.output.resolve()
    assert not out.exists() and out.is_relative_to(h.SCRATCH)
    assert source != out and source not in out.parents
    protected = {str(p.relative_to(source)): h.sha(p) for p in source.rglob('*') if p.is_file()}
    refs = set(NEW)
    thermal = None
    if args.thermal_manifest:
        thermal = json.loads(args.thermal_manifest.read_text())
        m.validate_thermal_manifest(thermal)
        refs.update({'D3', 'J4'})
    pcb_text = (source / 'stratolink.kicad_pcb').read_text()
    sch_text = (source / 'stratolink.kicad_sch').read_text()
    fps, syms = m.checked_nodes(pcb_text, 'footprint'), m.checked_nodes(sch_text, 'symbol')
    assert refs <= fps.keys() and refs <= syms.keys()
    table = cad.parse((source / 'fp-lib-table').read_text())
    local = [n for n in cad.nodes(table, 'lib') if cad.scalar(n, 'name') == 'lib']
    assert len(local) == 1 and cad.scalar(local[0], 'uri') == '${KIPRJMOD}/lib'
    pcb_edits, sch_edits, report = [], [], {}
    for ref in sorted(refs):
        fp, sym = fps[ref], syms[ref]
        old = fp[3][1]
        assert cad.prop(sym[3], 'Footprint') == old, ('Existing footprint field mismatch', ref)
        old_name = old.split(':', 1)[-1]
        name = old_name if old_name.startswith('Stratolink_v1p1_' + ref + '_') else 'Stratolink_v1p1_' + ref + '_' + old_name
        new = 'lib:' + name
        # A balanced expression replacement avoids native reserialization of the board.
        assert fp[2].startswith('(footprint ' + json.dumps(old))
        replacement = fp[2].replace('(footprint ' + json.dumps(old), '(footprint ' + json.dumps(new), 1)
        pcb_edits.append((fp[0], fp[1], replacement))
        fields = m.direct(sym[2], 'property')
        field = next(n for n in fields if n[3][1] == 'Footprint')
        assert sum(n[3][1] == 'Footprint' for n in fields) == 1
        field_text = field[2].replace(json.dumps(old), json.dumps(new), 1)
        sch_edits.append((sym[0], sym[1], edit.replace(sym[2], [(field[0], field[1], field_text)])))
        if thermal and ref in {'D3', 'J4'}:
            change = next(c for c in thermal['changes'] if c['reference'] == ref)
            pad = next(p for p in cad.nodes(fp[3], 'pad') if p[1] == change['pad'])
            assert cad.scalar(pad, 'uuid') == change['pad_uuid']
            assert {k: float(cad.scalar(pad, k)) for k in change['after']} == change['after']
        physical = copy.deepcopy(fp[3])
        physical[1] = '<footprint-library-id>'
        report[ref] = dict(old_id=old, new_id=new, pad_count=len(cad.nodes(fp[3], 'pad')),
                           physical_geometry_sha256=digest(physical))
    new_pcb, new_sch = edit.replace(pcb_text, pcb_edits), edit.replace(sch_text, sch_edits)
    # Compare complete parsed trees, allowing only the explicit library identities.
    expected = cad.parse(pcb_text)
    for fp in cad.nodes(expected, 'footprint'):
        ref = cad.prop(fp, 'Reference')
        if ref in refs:
            fp[1] = report[ref]['new_id']
    assert expected == cad.parse(new_pcb), 'Unexpected physical PCB change'
    expected = cad.parse(sch_text)
    for sym in cad.nodes(expected, 'symbol'):
        ref = cad.prop(sym, 'Reference')
        if ref in refs:
            next(p for p in cad.nodes(sym, 'property') if p[1] == 'Footprint')[2] = report[ref]['new_id']
    assert expected == cad.parse(new_sch), 'Unexpected schematic change'
    shutil.copytree(source, out)
    (out / 'stratolink.kicad_pcb').write_text(new_pcb)
    (out / 'stratolink.kicad_sch').write_text(new_sch)
    app = wx.App(False)
    board = pcbnew.LoadBoard(str(out / 'stratolink.kicad_pcb'))
    # Never save this in-memory board: native FootprintSave handles footprint
    # normalization, while the on-disk board retains its exact authored geometry.
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if ref not in refs:
            continue
        assert not cad.nodes(fps[ref][3], 'zone'), 'Embedded rule area requires separate normalization review'
        pcbnew.FootprintSave(str(out / 'lib'), fp)
        name = report[ref]['new_id'].split(':', 1)[1]
        library = pcbnew.FootprintLoad(str(out / 'lib'), name)
        assert library is not None and not fp.FootprintNeedsUpdate(library, 1), ('Native library mismatch', ref)
        assert len(list(library.Pads())) == report[ref]['pad_count']
        report[ref]['library_sha256'] = h.sha(out / 'lib' / (name + '.kicad_mod'))
        report[ref]['native_library_matches'] = True
    assert (out / 'stratolink.kicad_pcb').read_text() == new_pcb
    assert (out / 'stratolink.kicad_sch').read_text() == new_sch
    changed = {'stratolink.kicad_pcb', 'stratolink.kicad_sch'} | {
        'lib/' + entry['new_id'].split(':', 1)[1] + '.kicad_mod' for entry in report.values()}
    for rel, value in protected.items():
        assert h.sha(source / rel) == value, ('Source changed during freeze', rel)
        if rel not in changed:
            assert h.sha(out / rel) == value, ('Unrelated copied file changed', rel)
    result = dict(status='PASS', source=str(source), candidate=str(out), footprints=report,
                  pcb_physical_tree_identical=True, schematic_only_footprint_fields_changed=True,
                  total_footprints=len(fps), total_pads=sum(len(cad.nodes(f[3], 'pad')) for f in fps.values()),
                  input_pcb_sha256=protected['stratolink.kicad_pcb'],
                  input_schematic_sha256=protected['stratolink.kicad_sch'],
                  pcb_sha256=h.sha(out / 'stratolink.kicad_pcb'),
                  schematic_sha256=h.sha(out / 'stratolink.kicad_sch'),
                  thermal_manifest_sha256=h.sha(args.thermal_manifest) if args.thermal_manifest else None)
    (out / 'footprint-freeze.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
