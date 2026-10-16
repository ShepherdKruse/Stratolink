#!/usr/bin/env python3
"""Build downloadable KiCad bundles from a verified manufacturing manifest."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def digest(data):
    return hashlib.sha256(data).hexdigest()


def archive(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, data, compresslevel=9)
    return stream.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=ROOT / 'hardware/pcb')
    parser.add_argument('--manifest', type=Path,
                        default=ROOT / 'hardware/gerbers/v1.1-final-20261016/manifest.json',
                        help='Verified source manifest; select an older manifest to reproduce that revision.')
    parser.add_argument('--check', action='store_true', help='Verify stored bundles without writing.')
    args = parser.parse_args()
    manifest_path = args.manifest.resolve()
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    sources = {}
    for name, expected in manifest['source_files'].items():
        path = (args.project / name).resolve()
        if not path.is_relative_to(args.project.resolve()):
            raise SystemExit(f'Invalid source path: {name}')
        data = path.read_bytes()
        if digest(data) != expected:
            raise SystemExit(f'Source differs from selected review manifest: {name}. Use its matching project files.')
        sources[name] = data
    libraries = {name: data for name, data in sources.items()
                 if name.startswith(('lib/', '3d/')) or name in ('fp-lib-table', 'sym-lib-table')}
    readme = (
        'Stratolink v1.1 KiCad 10 review files\n\n'
        'Extract the whole archive before opening it. Open stratolink.kicad_pro.\n'
        'Keep lib/, 3d/, fp-lib-table and sym-lib-table beside the project.\n'
        'The project footprint library nickname is lib; its path is ${KIPRJMOD}/lib.\n'
        'The library-only ZIP supplies those four items. Extract it beside the\n'
        'matching v1.1 .kicad_pro/.kicad_sch/.kicad_pcb files. It contains no board.\n'
        'Do not mix libraries and boards from different revisions.\n\n'
        'Install KiCad 10 standard 3D models for the remaining standard model paths.\n'
        'This affects 3D previews only; all board footprints are included locally.\n'
        'U6 is present in CAD but omitted from the initial pilot assembly.\n'
        'Engineering review files, not factory or flight qualification.\n\n'
        'PCB SHA-256: ' + manifest['source_files']['stratolink.kicad_pcb'] + '\n'
        'Repository: https://github.com/Stratolink-hq/Stratolink/tree/review/hardware-v1.1\n'
    ).encode()
    variants = {
        'stratolink-v1.1-kicad.zip': {**{'stratolink-v1.1/' + n: d for n, d in sources.items()},
                                     'stratolink-v1.1/OPEN-ME.txt': readme},
        'stratolink-v1.1-libraries.zip': {**libraries, 'OPEN-ME.txt': readme},
    }
    output = {name: archive(files) for name, files in variants.items()}
    record = {
        'board_revision': 'v1.1 engineering review',
        'pcb_sha256': manifest['source_files']['stratolink.kicad_pcb'],
        'source_manifest': str(manifest_path.relative_to(ROOT)) if manifest_path.is_relative_to(ROOT) else str(manifest_path),
        'source_manifest_sha256': digest(manifest_bytes),
        'source_files': manifest['source_files'],
        'archives': {name: {'sha256': digest(output[name]),
                            'members': {n: digest(d) for n, d in sorted(files.items())}}
                     for name, files in variants.items()},
    }
    output['manifest.json'] = (json.dumps(record, indent=2, sort_keys=True) + '\n').encode()
    if args.check:
        stored = json.loads((HERE / 'manifest.json').read_text())
        for key in ('board_revision', 'pcb_sha256', 'source_manifest', 'source_manifest_sha256', 'source_files'):
            if stored[key] != record[key]:
                raise SystemExit(f'Download manifest is stale: {key}')
        if set(stored['archives']) != set(variants):
            raise SystemExit('Download archive list differs.')
        for name, files in variants.items():
            data = (HERE / name).read_bytes()
            expected = stored['archives'][name]
            if digest(data) != expected['sha256'] or expected['members'] != record['archives'][name]['members']:
                raise SystemExit(f'Download is stale: {name}')
            with zipfile.ZipFile(io.BytesIO(data)) as bundle:
                if len(bundle.namelist()) != len(files) or set(bundle.namelist()) != set(files):
                    raise SystemExit(f'Archive member list differs: {name}')
                for member, source in files.items():
                    if bundle.read(member) != source:
                        raise SystemExit(f'Archive member differs: {name}/{member}')
    else:
        for name, data in output.items():
            (HERE / name).write_bytes(data)
    print(f'{"Verified" if args.check else "Built"} {len(variants)} bundles from {len(sources)} verified source files.')


if __name__ == '__main__':
    main()
