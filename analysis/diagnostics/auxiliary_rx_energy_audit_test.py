#!/usr/bin/env python3
"""Regression for long auxiliary-RX WFI and energy accounting."""

from auxiliary_rx_energy_audit import build_audit


def main() -> None:
    audit = build_audit()
    assert audit["status"] == "PARTIAL_WFI_REPAIRED_EXACT_CURRENT_HIL_REQUIRED"
    assert not audit["passed"]
    assert audit["source_contract"] == {
        "full_cadence_s": 1200,
        "ctt_listen_ms": 60000,
        "ctt_enabled_in_flight": False,
        "relay_floor_mv": 4200,
        "solar_gate_mv": 3000,
        "shared_idle_uses_wfi": True,
        "wfi_explicitly_clears_sleepdeep": True,
        "relay_uses_shared_wfi": True,
        "ctt_uses_shared_wfi": True,
        "relay_watchdog_and_abort_checks_preserved": True,
        "ctt_watchdog_and_abort_checks_preserved": True,
        "mission_requires_full_tier_and_solar_surplus": True,
        "relay_capped_by_remaining_region_lease": True,
    }
    energy = audit["energy_screen"]
    assert round(energy["radio_rx_typical_lower_screen_j_per_window"], 6) == 25.574247
    assert round(energy["former_mcu_busy_spin_screen_j_per_window"], 6) == 23.249315
    assert round(energy["former_combined_screen_j_per_window"], 6) == 48.823562
    assert energy["repaired_total_j_per_window"] is None
    print("PASS: auxiliary RX WFI repair and non-overclaiming energy screen")


if __name__ == "__main__":
    main()
