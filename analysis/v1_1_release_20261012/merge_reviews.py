#!/usr/bin/env python3
"""Apply independently reviewed layout deltas to a fresh scratch project."""
from pathlib import Path
import argparse
import importlib.util
import json
import shutil

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('integration', HERE / 'build_integrated.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
cad, edit = h.cad, h.edit


def strip_fill(node):
    return [x for x in node if not (isinstance(x, list) and x and x[0] in
            {'filled_polygon', 'filled_areas_thickness'})]


def footprint_signature(node):
    # KiCad moves custom fields and supplies UUID/font defaults on native save.
    # It also absorbs the redundant Footprint field into the actual library ID.
    props = {x[1]: x[2] for x in node if isinstance(x, list) and x and x[0] == 'property'}
    if 'Footprint' in props:
        assert props.pop('Footprint') == node[1]
    return ([x for x in node if not (isinstance(x, list) and x and x[0] == 'property')], props)


def preserve_properties(reviewed, target):
    current = []
    for start, end, depth in edit.spans(target):
        if depth == 1 and target[start:end].startswith('(property '):
            current.append(target[start:end])
    remove = [(start, end, '') for start, end, depth in edit.spans(reviewed)
              if depth == 1 and reviewed[start:end].startswith('(property ')]
    reviewed = edit.replace(reviewed, remove)
    return reviewed.rstrip()[:-1] + '\n' + '\n'.join(current) + '\n)'


def merge_objects(text, base_text, reviewed_text, kinds):
    changes, additions, record = [], [], {}
    for kind in kinds:
        base, reviewed, target = [h.nodes(t, kind) for t in (base_text, reviewed_text, text)]
        compare = strip_fill if kind == 'zone' else footprint_signature if kind == 'footprint' else lambda x: x
        removed = base.keys() - reviewed.keys()
        added = reviewed.keys() - base.keys()
        changed = {key for key in base.keys() & reviewed.keys()
                   if compare(base[key][3]) != compare(reviewed[key][3])}
        for key in sorted(removed | changed):
            assert key in target and compare(target[key][3]) == compare(base[key][3]), ('Merge conflict', kind, key)
            old = target[key]
            replacement = '' if key in removed else reviewed[key][2]
            if kind == 'footprint' and key not in removed:
                replacement = preserve_properties(replacement, old[2])
            changes.append((old[0], old[1], replacement))
        for key in sorted(added):
            assert key not in target, ('Duplicate new object', kind, key)
            additions.append(reviewed[key][2])
        record[kind] = dict(removed=sorted(removed), added=sorted(added), changed=sorted(changed))
    text = edit.replace(text, changes)
    return text.rstrip()[:-1] + '\n' + '\n'.join(additions) + '\n)\n', record


def apply_u7(source, out):
    manifest = json.loads((HERE / 'identities/u7-verification.json').read_text())
    reviewed = Path(manifest['candidate'])
    baseline = h.SCRATCH / 'identities/metadata-candidate'
    assert manifest['status'] == 'PASS'
    for folder, expected in ((reviewed, manifest['pcb_sha256']), (baseline, manifest['baseline_sha256'])):
        assert h.sha(folder / 'stratolink.kicad_pcb') == expected
    pcb = out / 'stratolink.kicad_pcb'
    text, delta = merge_objects(pcb.read_text(), (baseline / pcb.name).read_text(),
                               (reviewed / pcb.name).read_text(), ['footprint', 'segment', 'via', 'zone'])
    assert delta['footprint']['changed'] == ['U7']
    # Old cached copper is not valid after inserting new vias/keepouts. Let the
    # native filler regenerate it before connectivity and clearance review.
    stale = []
    for start, end, depth in edit.spans(text):
        if depth == 2 and text[start:end].startswith(('(filled_polygon', '(filled_areas_thickness')):
            stale.append((start, end, ''))
    text = edit.replace(text, stale)
    pcb.write_text(text)
    libname = 'Stratolink_v1p1_U7_PQFN50P200X200100-12N.kicad_mod'
    assert h.sha(reviewed / 'lib' / libname) == manifest['u7_library_sha256']
    shutil.copyfile(reviewed / 'lib' / libname, out / 'lib' / libname)
    rule = (HERE / 'identities/u7-clearance-rule.kicad_dru').read_text()
    rules = out / 'stratolink.kicad_dru'
    assert rule.startswith('(version 1)')
    rules.write_text(rules.read_text() + '\n' + rule[len('(version 1)'):])
    return dict(review=manifest, delta=delta)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source, out = args.source.resolve(), args.output.resolve()
    assert source != out and source not in out.parents and not out.exists()
    protected = {str(p.relative_to(source)): h.sha(p) for p in source.rglob('*') if p.is_file()}
    shutil.copytree(source, out)
    report = dict(source=str(source), candidate=str(out), u7=apply_u7(source, out))
    assert protected == {str(p.relative_to(source)): h.sha(p) for p in source.rglob('*') if p.is_file()}
    report['files'] = {str(p.relative_to(out)): h.sha(p) for p in out.rglob('*') if p.is_file()}
    (out / 'review-merge.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(candidate=str(out), delta=report['u7']['delta']), indent=2))


if __name__ == '__main__':
    main()
