# Portable peer-review evidence

`verify_peer_evidence.py` supplements `hardware/pcb/verify_review_package.py`. It verifies repository-relative source and evidence hashes and checks that selected JSON findings explicitly identify the current PCB. It neither reruns KiCad nor establishes RF or flight performance. The existing package verifier still checks manufacturing outputs and historical AS7331 evidence.

The final peer manifest must be frozen after the final RF candidate, review reports and manufacturing package agree. No final manifest is created by the tests or by running the verifier.

Create an input JSON containing these three fields:

```json
{
  "review_evidence": ["analysis/v1_1_peer_review_20261014/digital/final-rf-scope.json"],
  "bindings": [{
    "evidence": "analysis/v1_1_peer_review_20261014/digital/final-rf-scope.json",
    "pointer": "/after_sha256",
    "source": "hardware/pcb/stratolink.kicad_pcb"
  }],
  "scope": "State exactly which checks passed and the remaining qualification limits."
}
```

The filenames above illustrate the format. Select the actual final evidence files and their actual hash fields. Bind each independent final PCB report; include scripts and necessary inputs for reproduction. Keep rejected or superseded studies clearly labeled as historical evidence.

From the checkout root:

```sh
python3 analysis/v1_1_peer_review_20261014/freeze_peer_evidence.py --inputs analysis/v1_1_peer_review_20261014/peer-evidence-inputs.json
python3 analysis/v1_1_peer_review_20261014/verify_peer_evidence.py
python3 analysis/v1_1_peer_review_20261014/test_peer_evidence.py
```

The freezer takes the complete native source list from `hardware/gerbers/v1.1-pilot/manifest.json`, checks it against current files, and pins the package manifest, input list and checker scripts. It refuses to replace an existing peer manifest. Both tools accept `--root` for another checkout. The verifier also accepts `--manifest`.

To integrate with another Python verifier, load this module with `importlib.util` and call `verify(root=checkout_root)`. A failed check raises an exception; success returns source, evidence and binding counts plus the manifest hash. All paths in the manifest remain repository-relative, including on a different machine.

The ten tests cover a relocated checkout, changed or missing files, stale but rehashed review evidence, duplicate JSON keys, unsafe paths, symlink escapes, malformed hashes, missing or duplicate bindings, failed publication and overwrite refusal. These are integrity tests using synthetic files, with no CAD or package writes.
