#!/usr/bin/env python3
"""Integrate the reviewed mask/assembly changes and redundant route removal in scratch."""
from pathlib import Path
import argparse, hashlib, importlib.util, json, re, shutil, subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = Path.home() / 'Repositories/ai-working/scratch/stratolink-bare-finish-20261012/combined-final'
CLI = '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
spec = importlib.util.spec_from_file_location('ground_builder', ROOT / 'analysis/v1_1_ground_20261012/build_candidate.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
cad = helper.cad


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def footprint(text, ref):
    for s, e, d in helper.spans(text):
        if d == 1:
            n = cad.parse(text[s:e])
            if n[0] == 'footprint' and cad.prop(n, 'Reference') == ref:
                return s, e, text[s:e]
    raise ValueError(ref)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mask', required=True, type=Path)
    ap.add_argument('--assembly', required=True, type=Path)
    args = ap.parse_args()
    before = json.loads((HERE / 'before.json').read_text())
    canonical = ROOT / 'hardware/pcb'
    protected = {p: sha(canonical / p) for p in before['canonical_hashes']}
    assert protected == before['canonical_hashes']
    source_hashes = {str(p): sha(p) for source in [args.mask, args.assembly]
                     for p in source.rglob('*') if p.is_file() and p.suffix != '.log'}
    original = subprocess.check_output(['git', 'show', before['baseline_commit'] + ':hardware/pcb/stratolink.kicad_pcb'], cwd=ROOT, text=True)
    for ref in ['AE1', 'AE2']:
        assert footprint(original, ref)[2] == footprint((args.mask / 'stratolink.kicad_pcb').read_text(), ref)[2]
    assert (args.mask / 'stratolink.kicad_pro').read_bytes() == (canonical / 'stratolink.kicad_pro').read_bytes()
    assert (args.assembly / 'stratolink.kicad_pro').read_bytes() == (canonical / 'stratolink.kicad_pro').read_bytes()
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ['stratolink.kicad_pcb', 'stratolink.kicad_pro', 'fp-lib-table', 'sym-lib-table']:
        shutil.copyfile(args.mask / name, OUT / name)
    shutil.copyfile(args.assembly / 'stratolink.kicad_sch', OUT / 'stratolink.kicad_sch')
    shutil.copytree(args.assembly / 'lib', OUT / 'lib', dirs_exist_ok=True, symlinks=False)
    for name in ['Stratolink_GNSS_Wire_PTH_D1p0.kicad_mod', 'Stratolink_LoRa_Wire_PTH_D1p0.kicad_mod']:
        p = OUT / 'lib' / name
        p.write_text(re.sub(r'(?m)^[\t ]+$', '', p.read_text()))
    if (args.assembly / '3d/antennas').exists():
        shutil.copytree(args.assembly / '3d/antennas', OUT / '3d/antennas', dirs_exist_ok=True, symlinks=False)
    pcb = OUT / 'stratolink.kicad_pcb'
    text = pcb.read_text()
    changes = []
    for ref in ['AE1', 'AE2']:
        s, e, old = footprint(text, ref)
        new = footprint((args.assembly / 'stratolink.kicad_pcb').read_text(), ref)[2]
        changes.append((s, e, new))
    for s, e, d in helper.spans(text):
        if d == 1:
            n = cad.parse(text[s:e])
            if n[0] == 'segment' and cad.scalar(n, 'uuid') == 'fa277942-2f97-4c70-a150-464479c3b65e':
                assert cad.scalar(n, 'net') == 'VSTOR' and cad.one(n, 'width') == ['0.25']
                changes.append((s, e, ''))
    assert len(changes) == 3
    pcb.write_text(re.sub(r'(?m)^[\t ]+$', '', helper.replace(text, changes)))
    pro = OUT / 'stratolink.kicad_pro'
    text = pro.read_text()
    old_rule = '"solder_mask_bridge": "error"'
    assert text.count(old_rule) == 1
    pro.write_text(text.replace(old_rule, '"solder_mask_bridge": "ignore"'))
    result = subprocess.run([CLI, 'pcb', 'drc', '--refill-zones', '--schematic-parity', '--format', 'json',
                             '--output', str(HERE / 'candidate-drc-project.json'), str(pcb)], capture_output=True, text=True, check=True)
    (OUT / 'build.log').write_text(result.stdout + result.stderr)
    assert all(sha(Path(p)) == h for p, h in source_hashes.items())
    assert all(sha(canonical / p) == h for p, h in protected.items())
    drc = json.loads((HERE / 'candidate-drc-project.json').read_text())
    files = {str(p.relative_to(OUT)): sha(p) for p in OUT.rglob('*')
             if p.is_file() and p.suffix not in ['.log', '.kicad_prl']}
    manifest = dict(baseline=before['baseline_commit'], candidate=str(OUT), mask_source=str(args.mask),
                    assembly_source=str(args.assembly), source_hashes=source_hashes, files=files,
                    removed_segment='fa277942-2f97-4c70-a150-464479c3b65e',
                    rule_change={'solder_mask_bridge': {'before': 'error', 'after': 'ignore',
                                  'reason': 'No solder mask on either face; all openings intentionally merge. Raw enabled-mask audit is retained.'}},
                    drc={k: len(drc[k]) for k in ['violations', 'unconnected_items', 'schematic_parity']})
    (HERE / 'candidate.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({k: v for k, v in manifest.items() if k not in ['source_hashes', 'files']}, indent=2))


if __name__ == '__main__':
    main()
