#!/usr/bin/env python3
"""Redaction boundary for the pending-MAC-request inventory."""

from __future__ import annotations

from ttn_pending_mac_audit import FIELD_MASK, safe_pending


def main() -> None:
    remote = {
        "ids": {"dev_eui": "secret"},
        "session": {"keys": "secret"},
        "mac_state": {
            "pending_requests": [
                {"cid": "CID_DEV_STATUS", "dev_status_req": {"x": "secret"}},
                {"cid": "CID_LINK_CHECK", "payload": "secret"},
            ],
        },
    }
    report = safe_pending("na", 200, remote)
    assert report["pending_request_count"] == 2
    assert report["pending_request_cids"] == [
        "CID_DEV_STATUS", "CID_LINK_CHECK"
    ]
    assert "secret" not in repr(report)
    assert "dev_eui" not in repr(report)
    assert FIELD_MASK == "mac_state.pending_requests"
    failed = safe_pending("eu", 403, {"message": "secret"})
    assert failed["pending_request_count"] is None
    assert "secret" not in repr(failed)
    print("PASS: pending TTN MAC audit is read-only and redacted")


if __name__ == "__main__":
    main()
