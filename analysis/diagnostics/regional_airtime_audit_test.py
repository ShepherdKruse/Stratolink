#!/usr/bin/env python3
"""Regressions for the source-bound regional airtime audit."""

from __future__ import annotations

from pathlib import Path
import shutil
import tempfile

from regional_airtime_audit import ROOT, audit


def main() -> None:
    current = audit()
    assert current["passed"]
    airtime = current["airtime"]
    assert airtime["primary_phy_bytes"] == 53
    assert airtime["primary_ms"] == 328.704
    assert airtime["maximum_aux_phy_bytes"] == 66
    assert airtime["maximum_aux_ms"] == 390.144
    assert airtime["maximum_aux_dwell_margin_ms"] == 9.856
    assert airtime["join_request_ms"] == 61.696
    assert airtime["normal_daily_ms"] == 27177.984
    assert airtime["modeled_fault_burst_plus_one_join_ms"] == 29211.904

    with tempfile.TemporaryDirectory(prefix="stratolink-airtime-") as raw:
        root = Path(raw)
        for relative in (
            "firmware/include/config.h",
            "firmware/include/telemetry.h",
            "firmware/include/lorawan.h",
            "firmware/src/lorawan.cpp",
        ):
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, destination)
        header = root / "firmware/include/lorawan.h"
        header.write_text(
            header.read_text(encoding="utf-8").replace(
                "#define LORAWAN_PAYLOAD_MAX 53",
                "#define LORAWAN_PAYLOAD_MAX 54",
            ),
            encoding="utf-8",
        )
        drift = audit(root)
        assert not drift["passed"]
        assert drift["airtime"]["maximum_aux_ms"] == 410.624
        assert not drift["gates"]["as923_maximum_aux_under_400ms"]

    print(
        "PASS: exact source constants stay below AS923 dwell/FUP limits and "
        "a one-byte maximum-payload drift fails closed"
    )


if __name__ == "__main__":
    main()
