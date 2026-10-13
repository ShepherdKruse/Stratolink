#!/usr/bin/env python3
"""Promote the frozen, independently reviewed finish/antenna ECO once."""
from pathlib import Path
from collections import Counter
import argparse, hashlib, json, shutil, subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CAD = ROOT / 'hardware/pcb'
CLI = '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


def signature(item):
    return json.dumps({k: item[k] for k in ['type', 'severity', 'description']}
                      | {'uuids': sorted(x['uuid'] for x in item.get('items', []))}, sort_keys=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--saved-editor-closed', action='store_true', required=True)
    parser.parse_args()
    before = json.loads((HERE / 'before.json').read_text())
    candidate = json.loads((HERE / 'candidate.json').read_text())
    review = json.loads((HERE / 'review/verification.json').read_text())
    baseline = json.loads((HERE / 'review/baseline-manifest.json').read_text())
    scope = json.loads((HERE / 'review/approved-scope.json').read_text())
    source = Path(candidate['candidate'])
    assert review['status'] == 'native, independent geometry and fabrication checks passed', review['status']
    assert review['all_physical_pad_sets_checked'] == 232 and review['unconnected'] == 0
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == before['baseline_commit']
    assert subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip() == before['branch']
    assert not subprocess.check_output(['git', 'diff', '--cached', '--name-only'], cwd=ROOT)
    assert not (CAD / '~stratolink.kicad_pcb.lck').exists()
    assert all(sha(ROOT / p) == h for p, h in before['unrelated_tracked_changes'].items())
    assert all(sha(CAD / p) == h for p, h in baseline['files'].items())
    assert all(sha(Path(p)) == h for p, h in review['source_hashes'].items())
    assert all(sha(source / p) == h for p, h in candidate['files'].items())
    new = ['lib/' + n for n in scope['new_library_files']]
    assert len(new) == 4 and all(not (CAD / p).exists() for p in new)
    copies = ['stratolink.kicad_pcb', 'stratolink.kicad_sch', 'stratolink.kicad_pro'] + new
    assert set(candidate['files']) - set(baseline['files']) == set(new)
    for name in copies:
        shutil.copyfile(source / name, CAD / name)
    assert all(sha(CAD / p) == h for p, h in candidate['files'].items())
    result = subprocess.run([CLI, 'pcb', 'drc', '--refill-zones', '--schematic-parity', '--format', 'json',
                             '--output', str(HERE / 'canonical-drc-project.json'), str(CAD / 'stratolink.kicad_pcb')],
                            capture_output=True, text=True, check=True)
    (source / 'canonical-check.log').write_text(result.stdout + result.stderr)
    actual = json.loads((HERE / 'canonical-drc-project.json').read_text())
    checked = json.loads((HERE / 'review/candidate-drc-project.json').read_text())
    categories = ['violations', 'unconnected_items', 'schematic_parity']
    assert all(Counter(map(signature, actual[c])) == Counter(map(signature, checked[c])) for c in categories)
    assert all(sha(CAD / p) == h for p, h in candidate['files'].items())
    assert all(sha(ROOT / p) == h for p, h in before['unrelated_tracked_changes'].items())
    output = dict(baseline=before['baseline_commit'], branch=before['branch'], source=str(source), canonical=str(CAD),
                  copied_files=copies, files=candidate['files'], source_matches_reviewed_candidate=True,
                  gui_closed_cleanly_before_promotion=True, canonical_reopened_in_kicad=False,
                  canonical_drc={c: len(actual[c]) for c in categories}, canonical_drc_signatures_match_reviewed=True,
                  unrelated_tracked_changes_preserved=len(before['unrelated_tracked_changes']))
    (HERE / 'promotion.json').write_text(json.dumps(output, indent=2) + '\n')
    print(json.dumps({k: v for k, v in output.items() if k != 'files'}, indent=2))


if __name__ == '__main__':
    main()
