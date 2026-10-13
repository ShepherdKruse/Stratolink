#!/usr/bin/env python3
"""Combine reviewed independent candidates in scratch, never canonical hardware."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCRATCH = Path.home() / 'Repositories/ai-working/scratch/stratolink-release-20261012'
OUT = SCRATCH / 'integrated'
CLI = '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
spec = importlib.util.spec_from_file_location('cad_edit', ROOT / 'analysis/v1_1_ground_20261012/build_candidate.py')
edit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(edit)
cad = edit.cad


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def nodes(text, kind):
    result = {}
    for start, end, depth in edit.spans(text):
        if depth != 1:
            continue
        value = cad.parse(text[start:end])
        if value[0] != kind:
            continue
        key = cad.prop(value, 'Reference') if kind in ('footprint', 'symbol') else cad.scalar(value, 'uuid')
        assert key and key not in result, ('Missing or duplicate object identity', kind, key)
        result[key] = (start, end, text[start:end], value)
    return result


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUT,
                        help='Fresh scratch folder; an existing project is never overwritten')
    args = parser.parse_args()
    OUT = args.output.resolve()
    assert OUT.is_relative_to(SCRATCH) and not OUT.exists(), 'Use a fresh output under the release scratch folder'
    metadata = SCRATCH / 'identities/metadata-candidate'
    headers = SCRATCH / 'headers/candidate'
    baseline = SCRATCH / 'baseline'
    rules = SCRATCH / 'rules'
    header_manifest = json.loads((HERE / 'headers/candidate.json').read_text())
    for name, expected in header_manifest['files'].items():
        assert sha(headers / name) == expected, ('Header candidate changed', name)
    protected = {p: sha(p) for p in (ROOT / 'hardware/pcb').glob('stratolink.kicad_*') if p.suffix in ('.kicad_pcb', '.kicad_sch', '.kicad_pro')}
    OUT.mkdir(parents=True, exist_ok=False)
    source_hashes = {}
    for p in metadata.rglob('*'):
        if p.is_file() and (p.is_relative_to(metadata / 'lib') or p.suffix in ('.kicad_pcb', '.kicad_sch', '.kicad_pro') or p.name in ('fp-lib-table', 'sym-lib-table')):
            rel = p.relative_to(metadata)
            dest = OUT / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, dest)
            source_hashes['metadata/' + str(rel)] = sha(p)
    model_files = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', '5997979:hardware/pcb/3d'], cwd=ROOT, text=True).splitlines()
    for name in model_files:
        p = OUT / '3d' / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(subprocess.check_output(['git', 'show', '5997979:hardware/pcb/3d/' + name], cwd=ROOT))
        source_hashes['baseline/3d/' + name] = sha(p)
    for p in headers.glob('lib/Stratolink_Programming*.kicad_mod'):
        shutil.copyfile(p, OUT / 'lib' / p.name)
    # Use the manifest rather than a naming convention for all header libraries.
    for name in header_manifest['libraries'].values():
        p = headers / 'lib' / Path(name).name
        shutil.copyfile(p, OUT / 'lib' / p.name)
        source_hashes['headers/lib/' + p.name] = sha(p)
    inventory = {}
    for filename, kind in [('stratolink.kicad_pcb', 'footprint'), ('stratolink.kicad_sch', 'symbol')]:
        text = (OUT / filename).read_text()
        target = nodes(text, kind)
        new = nodes((headers / filename).read_text(), kind)
        changes = [(target[ref][0], target[ref][1], new[ref][2]) for ref in ('J3', 'J4')]
        if kind == 'footprint':
            old_tracks = nodes((baseline / filename).read_text(), 'segment')
            new_tracks = nodes((headers / filename).read_text(), 'segment')
            target_tracks = nodes(text, 'segment')
            assert old_tracks.keys() <= new_tracks.keys()
            changed = [uid for uid in old_tracks if old_tracks[uid][3] != new_tracks[uid][3]]
            added = sorted(new_tracks.keys() - old_tracks.keys())
            assert len(changed) == 4 and len(added) == 2
            for uid in changed:
                assert target_tracks[uid][3] == old_tracks[uid][3], ('Conflicting segment change', uid)
                changes.append((target_tracks[uid][0], target_tracks[uid][1], new_tracks[uid][2]))
            text = edit.replace(text, changes)
            text = text.rstrip()[:-1] + '\n' + '\n'.join(new_tracks[uid][2] for uid in added) + '\n)\n'
            inventory['header_segment_changes'] = changed
            inventory['header_segment_additions'] = added
        else:
            text = edit.replace(text, changes)
        (OUT / filename).write_text(text)
        source_hashes['headers/' + filename] = sha(headers / filename)
    for filename in ('stratolink.kicad_pro', 'stratolink.kicad_dru'):
        shutil.copyfile(rules / filename, OUT / filename)
        source_hashes['rules/' + filename] = sha(rules / filename)
    gap = json.loads((HERE / 'headers/gap-delta.json').read_text())
    gap_path = Path(gap['candidate']) / 'stratolink.kicad_pcb'
    assert sha(gap_path) == gap['pcb_sha256']
    pcb_path = OUT / 'stratolink.kicad_pcb'
    text = pcb_path.read_text()
    target_tracks = nodes(text, 'segment')
    gap_tracks = nodes(gap_path.read_text(), 'segment')
    edits = []
    for item in gap['changes']:
        uid = item['uuid']
        old = target_tracks[uid]
        actual = [[round(float(x) * 1e6) for x in cad.one(old[3], key)] for key in ('start', 'end')]
        assert actual == item['before_nm']
        edits.append((old[0], old[1], gap_tracks[uid][2]))
    pcb_path.write_text(edit.replace(text, edits))
    source_hashes['headers/gap-delta'] = gap['pcb_sha256']
    inventory['header_gap_refinement'] = gap['changes']
    result = subprocess.run([CLI, 'pcb', 'drc', '--refill-zones', '--save-board', '--all-track-errors', '--schematic-parity', '--format', 'json', '--output', str(HERE / 'integrated-drc.json'), str(OUT / 'stratolink.kicad_pcb')], capture_output=True, text=True, check=True)
    (OUT / 'build.log').write_text(result.stdout + result.stderr)
    assert all(sha(p) == expected for p, expected in protected.items()), 'Canonical CAD changed during scratch build'
    manifest = dict(candidate=str(OUT), input_hashes=source_hashes, inventory=inventory, files={str(p.relative_to(OUT)): sha(p) for p in OUT.rglob('*') if p.is_file() and (p.suffix.startswith('.kicad_') or p.name in ('fp-lib-table', 'sym-lib-table'))})
    (HERE / 'integrated-build.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(result.stdout)
    drc = json.loads((HERE / 'integrated-drc.json').read_text())
    print(json.dumps({key: len(drc[key]) for key in ('violations', 'unconnected_items', 'schematic_parity')}))
    for item in drc['violations'] + drc['schematic_parity']:
        if item.get('severity') == 'error':
            print(json.dumps(item))


if __name__ == '__main__':
    main()
