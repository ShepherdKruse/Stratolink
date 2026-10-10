#!/usr/bin/env python3
"""Prove Board1 nonce readiness includes every configured flight region."""

import contextlib
import io
import json
from unittest.mock import patch

import ttn_devnonce_audit as audit


EXPECTED_BOARD1 = (
    ("na", "nam1.cloud.thethings.network", "TTN_NA_API_KEY", "stratolink", "stratolink-1"),
    ("eu", "eu1.cloud.thethings.network", "TTN_EU_API_KEY", "eu-stratolink", "stratolink-1-eu"),
    ("as", "eu1.cloud.thethings.network", "TTN_AS_API_KEY", "as-stratolink", "stratolink-1-as"),
    ("au", "nam1.cloud.thethings.network", "TTN_NA_API_KEY", "stratolink", "stratolink-1-au"),
)


def run(missing_au=False):
    calls = []

    def get(host, path, key):
        calls.append((host, path, key))
        if "/stratolink-1-au?" in path:
            if missing_au:
                return 404, {"message": "not registered"}
            return 200, {"used_dev_nonces": [3]}
        return 200, {"used_dev_nonces": [0]}

    out = io.StringIO()
    keys = {name: "test-only-placeholder" for _, _, name, _, _ in EXPECTED_BOARD1}
    with patch.object(audit, "load_values", return_value=keys), \
         patch.object(audit, "get_json", side_effect=get), \
         patch("sys.argv", ["ttn_devnonce_audit.py", "--device", "stratolink-1"]), \
         contextlib.redirect_stdout(out):
        audit.main()
    assert "test-only-placeholder" not in out.getvalue()
    return json.loads(out.getvalue()), calls


def main():
    assert audit.BOARD1_TARGETS == EXPECTED_BOARD1, "Board1 audit must cover all four regions"
    report, calls = run()
    assert len(calls) == 4
    assert [r["region"] for r in report["targets"]] == ["na", "eu", "as", "au"]
    assert report["global_max_seen"] == 3
    assert report["current_seed_safe"] is False
    assert report["longest_common_unused_run_start"] == 4
    assert report["longest_common_unused_run_length"] == 65532
    for target, call in zip(EXPECTED_BOARD1, calls):
        _, host, _, app, device = target
        assert call[0] == host
        assert call[1] == f"/js/applications/{app}/devices/{device}?field_mask=last_dev_nonce,used_dev_nonces,resets_join_nonces"
    missing, _ = run(missing_au=True)
    assert missing["targets"][-1]["status"] == 404
    assert missing["current_seed_safe"] is False
    assert missing["longest_common_unused_run_start"] is None
    assert missing["longest_common_unused_run_length"] is None
    assert [t[-1] for t in audit.TARGETS] == ["stratolink-2", "stratolink-2-eu", "stratolink-2-as"]
    print("PASS: Board1 nonce audit covers US/EU/AS/AU; missing regions cannot certify a safe journal")


if __name__ == "__main__":
    main()
