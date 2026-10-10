#!/usr/bin/env python3
"""Regression for redacted TTN Storage presence evidence."""

from __future__ import annotations

import base64

from ttn_storage_presence_audit import summarize


def row(device: str, when: str, counter: int) -> dict:
    return {
        "end_device_ids": {"device_id": device, "dev_addr": "260CACD0"},
        "received_at": when,
        "uplink_message": {
            "f_cnt": counter,
            "f_port": 1,
            "frm_payload": base64.b64encode(bytes(40)).decode("ascii"),
        },
    }


def main() -> None:
    records = [
        row("stratolink-2", "2026-07-27T10:01:35Z", 1),
        row("other-device", "2026-07-27T10:01:36Z", 9),
    ]
    report = summarize(
        records,
        "stratolink-2",
        after="2026-07-27T09:47:54Z",
        until="2026-07-27T10:02:00Z",
        expected_rows=1,
    )
    assert report["passed"] is True
    assert report["selected_rows"] == 1
    assert report["other_device_rows"] == 1
    assert report["first_f_cnt"] == 1
    rendered = repr(report)
    assert "stratolink-2" not in rendered
    assert "other-device" not in rendered
    assert "260CACD0" not in rendered
    assert "frm_payload" not in rendered

    assert summarize(
        records,
        "stratolink-2",
        after="2026-07-27T10:01:35Z",
        until=None,
        expected_rows=1,
    )["passed"] is False
    assert summarize(
        records,
        "stratolink-2",
        after="2026-07-27T09:47:54Z",
        until=None,
        expected_rows=2,
    )["passed"] is False
    print("PASS: TTN Storage presence evidence is authoritative and redacted")


if __name__ == "__main__":
    main()
