#!/usr/bin/env python3
"""Verify portable peer-review source/evidence hashes and explicit CAD bindings.

This supplements hardware/pcb/verify_review_package.py. It does not rerun
KiCad, qualify RF performance, or replace the historical AS7331 review.
"""
from __future__ import annotations
import argparse, hashlib, json, re
from pathlib import Path, PurePosixPath

SCHEMA = 'stratolink-peer-review-evidence-v1'
DEFAULT_MANIFEST = 'analysis/v1_1_peer_review_20261014/peer-evidence-manifest.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key: ' + key)
        result[key] = value
    return result


def read_json(path):
    return json.loads(path.read_text(), object_pairs_hook=unique_object)


def resolve(root, name):
    if not isinstance(name, str) or not name or '\\' in name:
        raise ValueError('Expected a nonempty repository-relative POSIX path')
    rel = PurePosixPath(name)
    if rel.is_absolute() or any(x in {'.', '..', ''} for x in name.split('/')) or ':' in name:
        raise ValueError('Unsafe or noncanonical path: ' + name)
    root = root.resolve()
    result = root.joinpath(*rel.parts).resolve()
    if not result.is_relative_to(root):
        raise ValueError('Path escapes repository: ' + name)
    return result


def pointer(document, path):
    if not isinstance(path, str) or not path.startswith('/'):
        raise ValueError('Binding needs a nonempty RFC6901 JSON pointer')
    value = document
    for token in path[1:].split('/'):
        if re.search(r'~(?:[^01]|$)', token):
            raise ValueError('Invalid JSON pointer escape')
        key = token.replace('~1', '/').replace('~0', '~')
        if isinstance(value, dict):
            value = value[key]
        elif isinstance(value, list) and re.fullmatch(r'0|[1-9][0-9]*', key):
            value = value[int(key)]
        else:
            raise ValueError('Binding pointer does not identify a value: ' + path)
    return value


def verify(root=None, manifest=None):
    """Return checked counts; raise ValueError/FileNotFoundError on any mismatch."""
    root = Path(root).resolve() if root else Path(__file__).resolve().parents[2]
    manifest = Path(manifest) if manifest else root / DEFAULT_MANIFEST
    if not manifest.is_absolute():
        manifest = root / manifest
    if not manifest.resolve().is_relative_to(root):
        raise ValueError('Evidence manifest is outside the checkout')
    m = read_json(manifest)
    if not isinstance(m, dict) or set(m) != {'schema', 'reviewed_sources', 'review_evidence', 'bindings', 'scope'}:
        raise ValueError('Unexpected manifest schema fields')
    if m['schema'] != SCHEMA or not isinstance(m['scope'], str) or not m['scope']:
        raise ValueError('Unsupported manifest schema or missing scope statement')
    all_names = set()
    counts = {}
    for section in ['reviewed_sources', 'review_evidence']:
        entries = m[section]
        if not isinstance(entries, dict) or not entries:
            raise ValueError('Missing nonempty ' + section)
        for name, digest in entries.items():
            if name in all_names:
                raise ValueError('Path appears in multiple categories: ' + name)
            all_names.add(name)
            if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
                raise ValueError('Invalid SHA256 for ' + name)
            path = resolve(root, name)
            if path == manifest.resolve():
                raise ValueError('Manifest cannot hash itself')
            if not path.is_file() or sha(path) != digest:
                raise ValueError('Hash verification failed: ' + name)
        counts[section] = len(entries)
    if not isinstance(m['bindings'], list) or not m['bindings']:
        raise ValueError('No evidence-to-source bindings')
    seen = set()
    for binding in m['bindings']:
        if not isinstance(binding, dict) or set(binding) != {'evidence', 'pointer', 'source'}:
            raise ValueError('Invalid source-binding fields')
        e, ptr, source = binding['evidence'], binding['pointer'], binding['source']
        key = (e, ptr, source)
        if key in seen:
            raise ValueError('Duplicate source binding')
        seen.add(key)
        if e not in m['review_evidence'] or source not in m['reviewed_sources']:
            raise ValueError('Binding references an unpinned file')
        actual = pointer(read_json(resolve(root, e)), ptr)
        if actual != m['reviewed_sources'][source]:
            raise ValueError('Evidence binds another CAD version: ' + e + ' ' + ptr)
    pcb = 'hardware/pcb/stratolink.kicad_pcb'
    if pcb not in m['reviewed_sources'] or not any(b['source'] == pcb for b in m['bindings']):
        raise ValueError('Final PCB hash is not bound to review evidence')
    counts['bindings'] = len(seen)
    counts['manifest_sha256'] = sha(manifest)
    return counts


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path)
    p.add_argument('--manifest', type=Path)
    a = p.parse_args()
    result = verify(a.root, a.manifest)
    print('PASS: ' + json.dumps(result, sort_keys=True))
