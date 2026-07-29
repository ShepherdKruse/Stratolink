#!/usr/bin/env python3
"""Pure evaluator and secret-boundary tests for TTN DevStatus follow-up."""

from __future__ import annotations

from ttn_devstatus_followup import FORBIDDEN_EVENTS, REQUIRED_EVENTS, evaluate


AFTER = "2026-07-27T08:18:35.634159117Z"
NEXT = "2026-07-27T08:39:32.000000000Z"


def event(name: str, when: str = NEXT) -> dict[str, str]:
    return {"name": name, "time": when, "secret": "not-retained"}


def main() -> None:
    pending, anchor = evaluate([], AFTER)
    assert pending["status"] == "PENDING" and anchor is None

    good = [event(name) for name in REQUIRED_EVENTS]
    report, anchor = evaluate(good, AFTER)
    assert report["passed"] is True and anchor == NEXT
    assert "secret" not in repr(report)

    for forbidden in FORBIDDEN_EVENTS:
        bad, _ = evaluate(good + [event(forbidden)], AFTER)
        assert bad["passed"] is False
        assert forbidden in bad["forbidden_events"]

    missing, _ = evaluate(
        [row for row in good if row["name"] != "as.up.data.forward"], AFTER
    )
    assert missing["passed"] is False
    assert missing["missing_required_events"]

    old = [event(name, AFTER) for name in REQUIRED_EVENTS]
    old_report, old_anchor = evaluate(old, AFTER)
    assert old_report["status"] == "PENDING" and old_anchor is None
    print("PASS: TTN DevStatus follow-up is exact, redacted, and fail-closed")


if __name__ == "__main__":
    main()
