#!/usr/bin/env python3

from low_rail_load_audit import audit


def main() -> None:
    result = audit()
    assert result["status"] == "BLOCKED_LOW_RAIL_THRESHOLDS_REQUIRE_EXACT_ASSEMBLY_HIL"
    screen = result["screen"]
    assert round(screen["gps_pessimistic_ohmic_drop_v"], 6) == 0.299
    assert round(screen["gps_floor_screened_vout_v"], 6) == 3.301
    assert round(screen["gps_vio_min_margin_v"], 6) == 0.601
    assert round(screen["gps_full_regulation_margin_v"], 6) == -0.011
    assert round(screen["tx_pessimistic_ohmic_drop_v"], 6) == 0.13156
    assert round(screen["tx_floor_screened_vout_v"], 6) == 2.86844
    assert result["gates"]["gps_floor_above_3v3_mode_vio_min_in_ohmic_screen"]
    assert result["gates"]["tx_floor_above_rak_vcc_min_in_ohmic_screen"]
    assert not result["passed"]
    print("PASS: low-rail component screen remains fail-closed pending exact HIL")


if __name__ == "__main__":
    main()
