#!/usr/bin/env python3
"""Regression for source-bound Class-A timing and the WFI power repair."""

from class_a_energy_audit import build_audit


def main() -> None:
    audit = build_audit()
    assert audit["status"] == "PARTIAL_WFI_REPAIRED_EXACT_CURRENT_HIL_REQUIRED"
    assert not audit["passed"]
    contract = audit["source_contract"]
    assert contract == {
        "ttn_assigned_rx_delay_default_s": 5,
        "preopen_ms_per_window": 250,
        "rx1_post_center_tail_ms": 500,
        "rx2_post_center_tail_ms": 740,
        "rx1_to_rx2_spacing_ms": 1000,
        "empty_rx_on_ms_per_primary": 1740,
        "tx_end_to_empty_rx2_close_ms": 6740,
        "non_rx_wait_ms_per_primary": 5000,
        "cpu_wait_uses_wfi": True,
        "wfi_explicitly_clears_sleepdeep": True,
        "freefall_preempts_wait": True,
        "otaa_wait_and_rx_use_wfi": True,
        "otaa_freefall_preempts_wait_and_rx": True,
    }
    energy = audit["energy_screen"]
    assert round(energy["prior_documented_one_second_rx_j_per_cycle"], 6) == 0.021353
    assert round(energy["actual_empty_radio_rx_typical_j_per_cycle"], 6) == 0.037154
    assert round(energy["former_five_second_busy_wait_screen_j_per_cycle"], 6) == 0.097059
    assert round(energy["former_combined_screen_j_per_cycle"], 6) == 0.134213
    assert round(energy["full_tier"]["former_combined_screen_j_per_day"], 3) == 9.663
    assert round(energy["reduced_tier"]["former_combined_screen_j_per_day"], 3) == 6.442
    print("PASS: Class-A timing, WFI repair, freefall preemption, and energy screen")


if __name__ == "__main__":
    main()
