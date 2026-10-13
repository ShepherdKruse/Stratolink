"""Verify the published v1.1 files against the existing review manifests."""

import hashlib
import json
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[2]
    package = root / "hardware/gerbers/v1.1-pilot"
    manifest = json.loads((package / "manifest.json").read_text())
    original_root = Path(manifest["source"]).parents[1]
    checks = []
    for key, base in (("source_files", root / "hardware/pcb"),
                      ("output_files", package)):
        checks.extend((base / name, digest) for name, digest in manifest[key].items())
    for name, digest in manifest["evidence_files"].items():
        checks.append((root / Path(name).relative_to(original_root), digest))
    review = root / "analysis/v1_1_release_20261012/as7331/review"
    final = json.loads((review / "final-review.json").read_text())
    checks.extend((review / name, digest) for name, digest in final["evidence_sha256"].items())
    failures = []
    for path, expected in checks:
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            failures.append(str(path.relative_to(root)))
    if failures:
        raise SystemExit("Hash verification failed:\n" + "\n".join(failures))
    print(f"PASS: {len(checks)} CAD, manufacturing and review evidence hashes match.")


if __name__ == "__main__":
    main()
