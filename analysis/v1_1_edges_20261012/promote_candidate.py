#!/usr/bin/env python3
"""Apply this reviewed ECO once, after closing the saved native PCB editor."""
from collections import Counter
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CANONICAL = ROOT / 'hardware/pcb'
CLI = '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


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
    source = Path(candidate['candidate'])
    assert review['status'].startswith('pass: scoped R2 CAD'), review['status']
    assert review['all_physical_pad_sets_checked'] == 232 and review['unconnected'] == 0
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == before['baseline_commit']
    assert subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip() == before['branch']
    assert not subprocess.check_output(['git', 'diff', '--cached', '--name-only'], cwd=ROOT)
    assert not (CANONICAL / '~stratolink.kicad_pcb.lck').exists(), 'Native editor still has the board open'
    assert all(sha(ROOT / p) == h for p, h in before['unrelated_tracked_changes'].items())
    assert all(sha(CANONICAL / p) == h for p, h in before['canonical_hashes'].items())
    assert all(sha(CANONICAL / p) == h for p, h in baseline['files'].items())
    assert all(sha(Path(p)) == h for p, h in review['source_hashes'].items())
    assert all(sha(source / p) == h for p, h in candidate['files'].items())
    new_libraries = ['lib/' + p for p in review['changed_libraries']]
    assert len(new_libraries) == 2 and all(not (CANONICAL / p).exists() for p in new_libraries)
    copies = ['stratolink.kicad_pcb', 'stratolink.kicad_sch'] + new_libraries
    for name in copies:
        shutil.copyfile(source / name, CANONICAL / name)
    expected = {str(Path(p).relative_to(source)): h for p, h in review['source_hashes'].items()}
    assert all(sha(CANONICAL / p) == h for p, h in expected.items())
    subprocess.run([CLI, 'pcb', 'drc', '--refill-zones', '--schematic-parity', '--format', 'json',
                    '--output', str(HERE / 'canonical-drc-project.json'),
                    str(CANONICAL / 'stratolink.kicad_pcb')], check=True)
    actual = json.loads((HERE / 'canonical-drc-project.json').read_text())
    checked = json.loads((HERE / 'review/candidate-drc-project.json').read_text())
    categories = ['violations', 'unconnected_items', 'schematic_parity']
    assert all(Counter(map(signature, actual[c])) == Counter(map(signature, checked[c])) for c in categories)
    assert all(sha(CANONICAL / p) == h for p, h in expected.items()), 'Read-only check changed a file'
    assert all(sha(ROOT / p) == h for p, h in before['unrelated_tracked_changes'].items())
    result = dict(baseline=before['baseline_commit'], branch=before['branch'], source=str(source),
                  canonical=str(CANONICAL), copied_files=copies, files=expected,
                  unrelated_tracked_changes_preserved=len(before['unrelated_tracked_changes']),
                  source_matches_reviewed_candidate=True, gui_closed_cleanly_before_promotion=True,
                  canonical_drc={c: len(actual[c]) for c in categories},
                  canonical_drc_signatures_match_reviewed=True,
                  canonical_reopened_in_kicad=False, unchanged_hashes_after_native_check=True)
    (HERE / 'promotion.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'files'}, indent=2))


if __name__ == '__main__':
    main()
