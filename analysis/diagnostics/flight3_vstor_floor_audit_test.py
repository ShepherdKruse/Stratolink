#!/usr/bin/env python3
"""Regression for the Flight-3 VSTOR-floor provenance audit."""

from flight3_vstor_floor_audit import audit


def main() -> None:
    result = audit()
    assert not result["passed"]
    assert result["status"] == (
        "BLOCKED_HISTORICAL_FLOOR_IS_NOT_BROWNOUT_METROLOGY"
    )
    assert result["flown_source"]["commit"] == "c4bd109"
    assert not result["gates"][
        "historical_3v32_is_actual_vstor_or_brownout_metrology"
    ]
    assert result["gates"][
        "current_source_init_and_calibration_failures_fail_closed"
    ]
    assert result["gates"][
        "current_source_refreshes_runtime_vdda_each_vstor_read"
    ]
    assert result["gates"][
        "current_source_rejects_pre_narrowing_vrefint_alias"
    ]
    telemetry = result["post_launch_telemetry"]
    assert telemetry["minimum_reported_v"] == 3.322
    assert telemetry["minimum_temperature_c_in_plateau"] == -42.1
    assert telemetry["plateau_rows_at_or_below_3v35"] >= 5
    assert telemetry["maximum_following_gap_h"] > 20.0
    print("PASS: Flight-3 3.32 V plateau is not treated as brownout metrology")


if __name__ == "__main__":
    main()
