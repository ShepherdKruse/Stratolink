#!/usr/bin/env python3
"""Load every footprint and resolve models from fresh download extractions.

Run with KiCad's bundled Python after build.py --check.
"""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile

import pcbnew
import wx


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scratch', type=Path, required=True)
    parser.add_argument('--standard-models', type=Path, required=True)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    source = here.parent / 'pcb'
    manifest = json.loads((here / 'manifest.json').read_text())
    assert sha(source / 'stratolink.kicad_pcb') == manifest['pcb_sha256']
    args.scratch.mkdir(parents=True, exist_ok=True)
    app = wx.App(False)
    report = {'pcb_sha256': manifest['pcb_sha256'], 'archives': []}
    for name, expected in manifest['archives'].items():
        archive = here / name
        assert sha(archive) == expected['sha256'], name
        with tempfile.TemporaryDirectory(prefix='kicad-download-', dir=args.scratch) as temp:
            target = Path(temp)
            with zipfile.ZipFile(archive) as bundle:
                assert len(bundle.namelist()) == len(expected['members'])
                assert set(bundle.namelist()) == set(expected['members'])
                for member in bundle.namelist():
                    assert (target / member).resolve().is_relative_to(target.resolve())
                    assert hashlib.sha256(bundle.read(member)).hexdigest() == expected['members'][member]
                bundle.extractall(target)
            project = target / 'stratolink-v1.1' if (target / 'stratolink-v1.1').is_dir() else target
            pcb = project / 'stratolink.kicad_pcb'
            board = pcbnew.LoadBoard(str(pcb if pcb.exists() else source / pcb.name))
            assert '${KIPRJMOD}/lib' in (project / 'fp-lib-table').read_text()
            missing = []
            loaded = []
            models = []
            for footprint in board.GetFootprints():
                ref = footprint.GetReference()
                name_in_library = str(footprint.GetFPID().GetLibItemName())
                local = pcbnew.FootprintLoad(str(project / 'lib'), name_in_library)
                if local is None:
                    missing.append({'reference': ref, 'footprint': name_in_library})
                else:
                    loaded.append(ref)
                for model in footprint.Models():
                    path = model.m_Filename.replace('${KIPRJMOD}', str(project))
                    for version in ('9', '10'):
                        path = path.replace('${KICAD' + version + '_3DMODEL_DIR}', str(args.standard_models))
                    assert '${' not in path, (ref, path)
                    resolved = Path(path)
                    assert resolved.is_file(), (ref, path)
                    models.append({'reference': ref, 'path': model.m_Filename, 'sha256': sha(resolved)})
            assert not missing, missing
            assert len(loaded) == 68 and len(models) == 63
            report['archives'].append({'archive': archive.name, 'sha256': sha(archive),
                                       'loaded_footprint_instances': len(loaded),
                                       'missing': missing, 'resolved_models': models})
    (here / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS: 68 footprint instances and 63 model attachments resolve from each bundle.')


if __name__ == '__main__':
    main()
