#!/usr/bin/env python3
"""Combine independently prepared local ECOs in scratch, never canonical CAD."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = 'd70a53d2093454084c9b1ae989d0276a88395334'
OUT = Path.home() / 'Repositories/ai-working/scratch/stratolink-edges-20261012/combined-r2'
CLI = '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
sys.path.insert(0, str(ROOT / 'analysis/v1_1_ground_20261012'))
# Import by path below avoids this script's own module name.
import importlib.util
spec = importlib.util.spec_from_file_location('ground_builder', ROOT / 'analysis/v1_1_ground_20261012/build_candidate.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
cad = helper.cad


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def segment_blocks(text):
    result = {}
    for start, end, depth in helper.spans(text):
        if depth != 1:
            continue
        node = cad.parse(text[start:end])
        if node[0] == 'segment':
            result[cad.scalar(node, 'uuid')] = (start, end, text[start:end], node)
    return result


def without_endpoints(node):
    return [x for x in node if not (isinstance(x, list) and x[0] in ['start', 'end'])]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--routing', type=Path, required=True)
    ap.add_argument('--rings', type=Path, required=True)
    args = ap.parse_args()
    source_files = [p for d in [args.routing, args.rings] for p in d.rglob('*')
                    if p.is_file() and p.suffix in ['.kicad_pcb', '.kicad_sch', '.kicad_pro', '.kicad_mod']]
    source_hashes = {str(p.resolve()): sha(p) for p in source_files}
    canonical = ROOT / 'hardware/pcb'
    protected = {str(p): sha(p) for p in canonical.glob('stratolink.kicad_*')
                 if p.suffix in ['.kicad_pcb', '.kicad_sch', '.kicad_pro']}
    baseline = subprocess.check_output(['git', 'show', BASE + ':hardware/pcb/stratolink.kicad_pcb'], cwd=ROOT, text=True)
    old = segment_blocks(baseline)
    routed = segment_blocks((args.routing / 'stratolink.kicad_pcb').read_text())
    ring_text = (args.rings / 'stratolink.kicad_pcb').read_text()
    ring = segment_blocks(ring_text)
    assert set(old) == set(ring) and all(old[k][3] == ring[k][3] for k in old), 'Ring source modified routing'
    assert not set(old) - set(routed), 'Unexpected deleted route'
    changed = [k for k in old if old[k][3] != routed[k][3]]
    added = sorted(set(routed) - set(old))
    assert len(changed) == 12 and len(added) == 1, (changed, added)
    for key in changed:
        assert without_endpoints(old[key][3]) == without_endpoints(routed[key][3])
        assert cad.scalar(routed[key][3], 'net') in ['+SOLAR', 'VSTOR', 'PA9']
    assert cad.scalar(routed[added[0]][3], 'net') == '+SOLAR'
    assert cad.one(routed[added[0]][3], 'width') == ['0.25']
    changes = [(ring[k][0], ring[k][1], routed[k][2]) for k in changed]
    combined = helper.replace(ring_text, changes)
    end = combined.rfind(')')
    combined = combined[:end] + '\t' + routed[added[0]][2] + '\n' + combined[end:]
    OUT.mkdir(parents=True, exist_ok=True)
    names = ['stratolink.kicad_sch', 'stratolink.kicad_pro', 'fp-lib-table', 'sym-lib-table']
    for name in names:
        shutil.copyfile(args.rings / name, OUT / name)
    # All library files are regular copies; nothing points into mutable canonical CAD.
    if (OUT / 'lib').exists():
        shutil.rmtree(OUT / 'lib')
    shutil.copytree(args.rings / 'lib', OUT / 'lib', symlinks=False)
    pcb = OUT / 'stratolink.kicad_pcb'
    pcb.write_text(combined)
    result = subprocess.run([CLI, 'pcb', 'drc', '--refill-zones', '--save-board', '--schematic-parity',
                             '--format', 'json', '--output', str(HERE / 'candidate-drc-project.json'), str(pcb)],
                            check=True, capture_output=True, text=True)
    (OUT / 'build.log').write_text(result.stdout + result.stderr)
    assert all(sha(Path(p)) == h for p, h in source_hashes.items())
    assert all(sha(Path(p)) == h for p, h in protected.items())
    drc = json.loads((HERE / 'candidate-drc-project.json').read_text())
    manifest = dict(baseline=BASE, candidate=str(OUT), routing_source=str(args.routing), rings_source=str(args.rings),
                    changed_segments=sorted(changed), added_segments=added, source_hashes=source_hashes,
                    files={n: sha(OUT / n) for n in ['stratolink.kicad_pcb'] + names},
                    library_files={p.name: sha(p) for p in sorted((OUT / 'lib').iterdir()) if p.is_file()},
                    counts={k: len(drc[k]) for k in ['violations', 'unconnected_items', 'schematic_parity']})
    (HERE / 'candidate.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({k: v for k, v in manifest.items() if k not in ['source_hashes', 'library_files']}, indent=2))


if __name__ == '__main__':
    main()
