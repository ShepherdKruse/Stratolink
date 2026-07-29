#!/usr/bin/env python3
"""Regression for retained GNSS-region lease provenance across resets."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MAIN = (ROOT / "firmware/src/main.cpp").read_text(encoding="utf-8")
POWER = (ROOT / "firmware/src/power_manager.cpp").read_text(encoding="utf-8")
REGION_HEADER = (ROOT / "firmware/include/region_manager.h").read_text(
    encoding="utf-8"
)
REGION_SOURCE = (ROOT / "firmware/src/region_manager.cpp").read_text(
    encoding="utf-8"
)
HIL_GENERATOR = (ROOT / "analysis/diagnostics/generate_flight_hil.py").read_text(
    encoding="utf-8"
)
MAX_AGE = 1800
RESET_CHARGE = 300


def restore(lease: int | None) -> tuple[int, bool, bool]:
    age = 0
    trusted = lease is not None
    if trusted:
        age = lease
    known = trusted and age < MAX_AGE
    return age, trusted, known


def account_and_persist(age: int, elapsed: int, trusted: bool) -> int | None:
    age = min(0xFFFFFFFF, age + elapsed)
    return age if trusted else None


def main() -> None:
    # Source wiring: all physical TAMP writes pass through the provenance gate.
    assert MAIN.count("power_manager_save_region_lease(region_fix_age_sec)") == 1
    assert "if (region_lease_trusted)" in MAIN
    assert "region_lease_trusted = boot_lease_precharge_ok &&\n                power_manager_load_region_lease" in MAIN
    assert "region_known = region_lease_trusted &&" in MAIN
    assert "region_lease_trusted = true;" in MAIN
    # Normal end-of-cycle, spurious-wake, freefall-abort, GPS-interrupt, and
    # optical-quiescence early-return paths must all charge retained age.
    assert MAIN.count("persist_region_lease_if_trusted();") == 5
    assert "symbols['region_lease_trusted']['address']" in HIL_GENERATOR
    assert "if (!power_manager_save_region_lease(region_fix_age_sec))" in MAIN
    assert "region_known = false;\n            region_lease_trusted = false;" in MAIN
    assert "for (uint8_t attempt = 0; attempt < 3; ++attempt)" in POWER
    assert "static bool invalidate_session_and_lease_markers(void)" in POWER
    assert POWER.count("(void)invalidate_session_and_lease_markers();") == 2
    assert "return invalidate_session_and_lease_markers();" in POWER
    assert "#define STRATO_LEASE_WORD       18" in POWER
    assert "tamp_lease_record_encode(age_sec)" in POWER
    assert "tamp_lease_record_decode(record, &decoded_age)" in POWER
    assert "REGION_FIX_MAX_AGE_SEC <= TAMP_LEASE_AGE_MASK" in POWER
    assert "if (!lorawan_joined())" in MAIN
    assert "bool region_changed = lorawan_current_region() != region_before;" in MAIN
    assert MAIN.count("region_tx_allowed_now(cycle_started_ms)") == 4
    assert "region_fix_remaining_tx_ms(live_age) == 0u" in MAIN
    assert "live_region_age_sec = region_fix_age_advance(" in MAIN
    assert "relay_region_budget_ms = region_fix_remaining_tx_ms(" in MAIN
    assert "relay_window_budget, RELAY_FLOOR_MV, meshtastic_enabled" in MAIN
    assert "relay_region_budget_ms - ctt_used" in MAIN
    assert "sleep_lease_charge_sec =\n        region_sleep_age_charge_sec(sleep_sec)" in MAIN
    assert "#define REGION_RTC_CONFIGURED_LSI_HZ 32000u" in REGION_HEADER
    assert "#define REGION_RTC_MIN_LSI_HZ        29500u" in REGION_HEADER
    assert "(uint64_t)REGION_RTC_CONFIGURED_LSI_HZ" in REGION_SOURCE
    assert "(uint64_t)REGION_RTC_MIN_LSI_HZ - 1u" in REGION_SOURCE
    assert "scaled > UINT32_MAX ? UINT32_MAX" in REGION_SOURCE
    assert "#define REGION_RESET_UNACCOUNTED_CHARGE_SEC 300u" in REGION_HEADER
    assert "bool boot_lease_precharge_ok = true;" in MAIN
    assert "boot_lease_age_sec = region_fix_age_advance(" in MAIN
    assert "REGION_RESET_UNACCOUNTED_CHARGE_SEC" in MAIN
    assert "if (!power_manager_save_region_lease(boot_lease_age_sec))" in MAIN
    assert "boot_lease_precharge_ok = false;" in MAIN
    assert "region_lease_trusted = boot_lease_precharge_ok &&" in MAIN
    assert MAIN.index("power_manager_load_region_lease(&boot_lease_age_sec)") < MAIN.index("power_adc_init();")

    # Former fault: valid session + absent/corrupt lease stayed quiet for one
    # boot, then normal accounting published age~1800 from an untrusted zero.
    # The second reset could consequently authorize the stale session.
    age, trusted, known = restore(None)
    assert not trusted and not known
    persisted = account_and_persist(age, 1200, trusted)
    assert persisted is None
    _, trusted2, known2 = restore(persisted)
    assert not trusted2 and not known2

    # A genuinely loaded lease remains persistable but expires normally.
    age, trusted, known = restore(0)
    assert trusted and known
    persisted = account_and_persist(age, MAX_AGE + 1, trusted)
    assert persisted == MAX_AGE + 1
    _, trusted2, known2 = restore(persisted)
    assert trusted2 and not known2

    # A fresh PVT is the other allowed provenance root.
    persisted = account_and_persist(0, 1200, True)
    assert persisted == 1200
    _, trusted2, known2 = restore(persisted)
    assert trusted2 and known2

    # A second cycle without a fix begins around age 1200. The old code opened
    # the complete 1200 s relay window because it checked only at entry; that
    # crossed the 1800 s RF lease halfway through. The repaired caller computes
    # a live age, leaves one whole-second guard, and caps the TX-capable window.
    stale_cycle_start_age = 1200
    active_sec = 40
    live_age = min(0xFFFFFFFF, stale_cycle_start_age + active_sec)
    remaining_tx_ms = max(0, MAX_AGE - live_age - 1) * 1000
    assert remaining_tx_ms == 559000
    assert remaining_tx_ms < 1200 * 1000
    assert live_age + remaining_tx_ms // 1000 < MAX_AGE

    # STM32WLE5 LSI can be 29.5 kHz while STM32RTC divides for 32 kHz. A
    # nominal 1200 s STOP can therefore occupy 1301.7 s of real time. Retained
    # authorization charges the ceiling, so oscillator tolerance only expires
    # the lease earlier; it can never extend it.
    nominal_sleep = 1200
    charged_sleep = (nominal_sleep * 32000 + 29500 - 1) // 29500
    assert charged_sleep == 1302
    assert charged_sleep >= nominal_sleep * 32000 / 29500

    # A reset before the normal measured-time commit cannot freeze the lease.
    # Every retained boot first reserves five minutes; the sixth consecutive
    # no-fix reset reaches the 30-minute deadline and is RF-ineligible. A
    # failed precharge explicitly blocks trust in the same boot even if an old
    # marker remains readable.
    reset_age = 0
    for reset_count in range(1, 7):
        reset_age = min(0xFFFFFFFF, reset_age + RESET_CHARGE)
        assert (reset_age < MAX_AGE) == (reset_count < 6)
    precharge_ok = False
    old_marker_still_readable = True
    trusted_after_failed_commit = precharge_ok and old_marker_still_readable
    assert not trusted_after_failed_commit

    # A failed old-session clear changes RAM to the new region but leaves it
    # unjoined. The next fresh fix therefore sees region_changed=False; retry
    # must key on unjoined state rather than region_changed alone.
    ram_region = "EU868"
    region_changed = ram_region != "EU868"
    joined = False
    assert not region_changed and not joined
    clear_retried = not joined
    assert clear_retried

    print("PASS: missing/corrupt region lease cannot self-renew across reset")


if __name__ == "__main__":
    main()
