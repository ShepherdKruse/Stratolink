#!/usr/bin/env python3
"""Capture current and reviewed CAD; apply authoritative rules to scratch only."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
FROZEN = Path('/Users/twarn/Repositories/ai-working/worktrees/Stratolink/hardware-v1.1-review')
SCRATCH = Path('/Users/twarn/Repositories/ai-working/scratch/stratolink-final-sweep-20261016/electrical')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def capture(source, destination, names):
    before = {name: sha(source / name) for name in names}
    destination.mkdir(parents=True, exist_ok=False)
    for name in names:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)
    assert before == {name: sha(source / name) for name in names}, 'Source changed during capture'
    assert before == {name: sha(destination / name) for name in names}, 'Copy mismatch'
    return before

def main():
    manifest = json.loads((FROZEN / 'hardware/gerbers/v1.1-pilot/manifest.json').read_text())
    names = sorted(manifest['source_files'])
    SCRATCH.mkdir(parents=True, exist_ok=False)
    frozen = capture(FROZEN / 'hardware/pcb', SCRATCH / 'frozen', names)
    assert frozen == manifest['source_files']
    current = capture(ROOT / 'hardware/pcb', SCRATCH / 'current', names)
    shutil.copytree(SCRATCH / 'current', SCRATCH / 'current-strict')
    for name in ('stratolink.kicad_pro', 'stratolink.kicad_dru'):
        shutil.copyfile(SCRATCH / 'frozen' / name, SCRATCH / 'current-strict' / name)
    project = json.loads((SCRATCH / 'frozen/stratolink.kicad_pro').read_text())
    settings = project['board']['design_settings']
    result = {
        'captured_utc': datetime.now(timezone.utc).isoformat(),
        'frozen_git_head': subprocess.check_output(['git', '-C', str(FROZEN), 'rev-parse', 'HEAD'], text=True).strip(),
        'frozen_source': str(FROZEN / 'hardware/pcb'), 'current_source': str(ROOT / 'hardware/pcb'),
        'scratch': str(SCRATCH), 'frozen_files': frozen, 'current_files': current,
        'source_file_differences': [name for name in names if frozen[name] != current[name]],
        'authoritative_project_sha256': frozen['stratolink.kicad_pro'],
        'authoritative_custom_rules_sha256': frozen['stratolink.kicad_dru'],
        'drc_rules': settings['rules'], 'drc_rule_severities': settings['rule_severities'],
        'drc_exclusions': settings['drc_exclusions'], 'erc_exclusions': project['erc']['erc_exclusions'],
        'ignored_drc_categories': [name for name, value in settings['rule_severities'].items() if value == 'ignore'],
        'source_CAD_edited': False,
    }
    (HERE / 'capture.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in ('captured_utc', 'frozen_git_head', 'scratch', 'source_file_differences')}, indent=2))

if __name__ == '__main__':
    main()
