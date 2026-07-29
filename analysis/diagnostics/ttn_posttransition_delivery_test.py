#!/usr/bin/env python3
"""Adversarial regression for corrected post-transition delivery proof."""

from __future__ import annotations

from copy import deepcopy

from ttn_posttransition_delivery import evaluate


EVENTS = {
    "status": "FAIL_FOLLOWING_UPLINK",
    "events": [
        {"name": "ns.up.data.receive"},
        {"name": "ns.up.data.process"},
        {"name": "as.up.data.receive"},
        {"name": "as.up.data.forward"},
    ],
    "forbidden_events": [],
    "missing_required_events": ["as.packages.storage.up.store"],
    "pending_requests_clear": True,
    "uplink_received_utc": "2026-07-27T10:01:35.631117584Z",
}
STORAGE = {
    "passed": True,
    "selected_rows": 1,
    "first_received_at": "2026-07-27T10:01:35.832312164Z",
    "last_received_at": "2026-07-27T10:01:35.832312164Z",
}
SUPABASE = [{
    "device_id": "stratolink-2",
    "time": "2026-07-27T10:01:35.832312+00:00",
}]
REMEDIATION = {
    "passed": True,
    "readback": {
        "all_regions_uplink_enabled": True,
        "all_regions_join_accept_disabled": True,
    },
}


def main() -> None:
    assert evaluate(EVENTS, STORAGE, SUPABASE, REMEDIATION)["passed"] is True
    mutations = []
    value = deepcopy(EVENTS)
    value["events"] = value["events"][:-1]
    mutations.append((value, STORAGE, SUPABASE, REMEDIATION))
    value = deepcopy(EVENTS)
    value["forbidden_events"] = ["ns.mac.command.unanswered"]
    mutations.append((value, STORAGE, SUPABASE, REMEDIATION))
    value = deepcopy(EVENTS)
    value["missing_required_events"] = ["as.packages.storage.up.store", "x"]
    mutations.append((value, STORAGE, SUPABASE, REMEDIATION))
    value = deepcopy(STORAGE)
    value["passed"] = False
    mutations.append((EVENTS, value, SUPABASE, REMEDIATION))
    value = deepcopy(SUPABASE)
    value[0]["time"] = "2026-07-27T10:01:36Z"
    mutations.append((EVENTS, STORAGE, value, REMEDIATION))
    value = deepcopy(REMEDIATION)
    value["readback"]["join_accept_disabled"] = False
    value["readback"]["all_regions_join_accept_disabled"] = False
    mutations.append((EVENTS, STORAGE, SUPABASE, value))
    for arguments in mutations:
        assert evaluate(*arguments)["passed"] is False
    print("PASS: corrected delivery proof rejects missing or mismatched evidence")


if __name__ == "__main__":
    main()
