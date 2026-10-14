#!/usr/bin/env python3
"""Explicitly freeze a peer evidence manifest after the final package is built.

Inputs JSON has review_evidence (list of repository-relative files), bindings
(list of evidence/pointer/source dictionaries), and scope (review limitations).
Source hashes come from the manufacturing manifest and must match current CAD.
The verifier, freezer, input list and package manifest are pinned automatically.
No CAD, package, historical evidence, or existing manifest is overwritten.
"""
import argparse, json, os, tempfile
from pathlib import Path
import verify_peer_evidence as v


def freeze(root, package_manifest, inputs, output):
    root = root.resolve()
    def relative(path):
        path = path.resolve()
        if not path.is_relative_to(root):
            raise ValueError('Manifest inputs must be within the checkout')
        return path.relative_to(root).as_posix()
    package_manifest = root / package_manifest
    inputs = root / inputs
    output = root / output
    for path in [package_manifest, inputs, output]:
        v.resolve(root, relative(path))
    if output.exists():
        raise ValueError('Refusing to overwrite existing evidence manifest')
    spec = v.read_json(inputs)
    if not isinstance(spec, dict) or set(spec) != {'review_evidence', 'bindings', 'scope'}:
        raise ValueError('Unexpected freeze-input fields')
    paths = spec['review_evidence']
    if not isinstance(paths, list) or not paths or len(set(paths)) != len(paths):
        raise ValueError('Evidence list must be nonempty and unique')
    package = v.read_json(package_manifest)
    source_hashes = package.get('source_files')
    if not isinstance(source_hashes, dict) or not source_hashes:
        raise ValueError('Manufacturing manifest has no source hashes')
    sources = {}
    for name, digest in source_hashes.items():
        # Validate the individual package-relative component before adding prefix.
        v.resolve(root / 'hardware/pcb', name)
        sources['hardware/pcb/' + name] = digest
    evidence = {}
    own_dir = 'analysis/v1_1_peer_review_20261014/'
    required = [relative(package_manifest), relative(inputs),
                own_dir + 'verify_peer_evidence.py', own_dir + 'freeze_peer_evidence.py']
    for name in [*paths, *required]:
        evidence[name] = v.sha(v.resolve(root, name))
    m = {'schema': v.SCHEMA, 'reviewed_sources': sources, 'review_evidence': evidence,
         'bindings': spec['bindings'], 'scope': spec['scope']}
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.peer-evidence-', suffix='.json', dir=output.parent)
    candidate = Path(temporary)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(json.dumps(m, indent=2, sort_keys=True) + '\n')
        v.verify(root, candidate)
        # Atomic exclusive publication; do not replace a concurrent freeze.
        os.link(candidate, output)
    finally:
        candidate.unlink(missing_ok=True)
    return v.verify(root, output)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    p.add_argument('--package-manifest', type=Path, default=Path('hardware/gerbers/v1.1-pilot/manifest.json'))
    p.add_argument('--inputs', type=Path, required=True)
    p.add_argument('--output', type=Path, default=Path(v.DEFAULT_MANIFEST))
    a = p.parse_args()
    print(json.dumps(freeze(a.root, a.package_manifest, a.inputs, a.output), sort_keys=True))
