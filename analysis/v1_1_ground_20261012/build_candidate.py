#!/usr/bin/env python3
"""Recreate the scoped ground correction in scratch; never write canonical CAD."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = 'c3d70a429a95591607341d57bf16ee153972da71'
OUT = Path.home() / 'Repositories/ai-working/scratch/stratolink-zones-20261012/combined'
CLI = '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
BACK_ZONE = 'e9b71a22-0a8a-41f9-b5c4-115945b7ef58'
LIB = 'lib/PQFN50P200X200100-12N.kicad_mod'
sys.path.insert(0, str(ROOT / 'analysis/v1_1_solar_attachments_20261012/layout'))
import cad_helpers as cad


def spans(text):
    stack, quoted, escaped = [], False, False
    for i, c in enumerate(text):
        if quoted:
            if escaped:
                escaped = False
            elif c == '\\':
                escaped = True
            elif c == '"':
                quoted = False
        elif c == '"':
            quoted = True
        elif c == '(':
            stack.append(i)
        elif c == ')':
            yield stack.pop(), i + 1, len(stack)
    assert not stack and not quoted


def replace(text, changes):
    for start, end, new in sorted(changes, reverse=True):
        text = text[:start] + new + text[end:]
    return text


def pad_overrides(text, overrides):
    changes = []
    for start, end, depth in spans(text):
        if depth != 1:
            continue
        node = cad.parse(text[start:end])
        if node[0] != 'pad' or node[1] not in overrides:
            continue
        assert cad.one(node, 'zone_connect') is None
        changes.append((start, end, text[start:end - 1] +
                        '\t(zone_connect %d)\n\t)' % overrides[node[1]]))
    assert len(changes) == len(overrides)
    return replace(text, changes)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    protected = {p: sha(p) for p in (ROOT / 'hardware/pcb').glob('stratolink.kicad_*')
                 if p.suffix in {'.kicad_pcb', '.kicad_sch', '.kicad_pro'}}
    names = ['stratolink.kicad_pcb', 'stratolink.kicad_sch', 'stratolink.kicad_pro',
             'fp-lib-table', 'sym-lib-table']
    libs = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only',
                                    BASE + ':hardware/pcb/lib'], cwd=ROOT, text=True).splitlines()
    for name in names + ['lib/' + n for n in libs]:
        dest = OUT / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        assert not dest.is_symlink()
        dest.write_bytes(subprocess.check_output(['git', 'show', BASE + ':hardware/pcb/' + name], cwd=ROOT))
    pcb = OUT / 'stratolink.kicad_pcb'
    original = pcb.read_text()
    changes = []
    for start, end, depth in spans(original):
        if depth != 1:
            continue
        text = original[start:end]
        node = cad.parse(text)
        if node[0] == 'zone' and cad.scalar(node, 'uuid') == BACK_ZONE:
            changes.append((start, end, ''))
        elif node[0] == 'footprint':
            ref = cad.prop(node, 'Reference')
            if ref == 'U7':
                changes.append((start, end, pad_overrides(text, {'5': 0, '7': 0, '8': 0})))
            elif ref == 'J20':
                changes.append((start, end, pad_overrides(text, {'5': 2})))
    assert len(changes) == 3
    pcb.write_text(replace(original, changes))
    lib = OUT / LIB
    lib.write_text(pad_overrides(lib.read_text(), {'5': 0, '7': 0, '8': 0}))
    report = HERE / 'candidate-drc-project.json'
    command = [CLI, 'pcb', 'drc', '--refill-zones', '--save-board', '--schematic-parity',
               '--format', 'json', '--output', str(report), str(pcb)]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    (OUT / 'build.log').write_text(result.stdout + result.stderr)
    assert all(sha(p) == h for p, h in protected.items()), 'Canonical CAD changed during scratch build'
    drc = json.loads(report.read_text())
    manifest = dict(baseline=BASE, candidate=str(OUT),
                    changes={'removed_zone': BACK_ZONE, 'U7_trace_fed_pads': ['5', '7', '8'],
                             'J20_solid_pad': '5'},
                    files={n: sha(OUT / n) for n in names + [LIB]},
                    drc={k: len(drc[k]) for k in ['violations', 'unconnected_items', 'schematic_parity']})
    (HERE / 'candidate.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
