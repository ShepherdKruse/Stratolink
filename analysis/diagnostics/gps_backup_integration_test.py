#!/usr/bin/env python3
"""Lock GNSS standby confirmation and main-loop fail-closed integration."""

from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
GPS = ROOT / "firmware/src/gps_ublox.cpp"
MAIN = ROOT / "firmware/src/main.cpp"
HEADER = ROOT / "firmware/include/gps_ublox.h"
POLICY = ROOT / "firmware/include/gps_backup_policy.h"
CONFIG = ROOT / "firmware/include/config.h"


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def main() -> None:
    gps = compact(GPS.read_text(encoding="utf-8"))
    main_source = compact(MAIN.read_text(encoding="utf-8"))
    header = compact(HEADER.read_text(encoding="utf-8"))
    policy = compact(POLICY.read_text(encoding="utf-8"))
    config = compact(CONFIG.read_text(encoding="utf-8"))

    assert "bool gps_ublox_sleep(void);" in header
    assert "#define GPS_BACKUP_CONFIRM_MS 350u" in policy
    assert "#define GPS_BACKUP_MAX_ATTEMPTS 3u" in policy
    assert "#define GPS_BACKUP_RESET_FLOOR_MV 4400u" in policy
    assert "#define GPS_BEGIN_MAX_WAIT_MS 1100u" in config
    assert gps.count("gnss.begin(GPS_SERIAL, GPS_BEGIN_MAX_WAIT_MS)") == 2
    assert "UBLOX_CFG_UART1OUTPROT_NMEA, 0" in gps
    assert "UBLOX_CFG_RATE_MEAS, 100" in gps
    assert "UBLOX_CFG_RATE_NAV, 1" in gps
    assert "UBLOX_CFG_MSGOUT_UBX_NAV_EOE_UART1, 1" in gps
    assert "gps_wait_for_nav_eoe_marker" in gps
    assert (
        "VAL_RXM_PMREQ_WAKEUPSOURCE_UARTRX, true, 0" in gps
    ), "input-only PMREQ must not masquerade a quiet timeout as an ACK"
    assert "gps_backup_decide(marker_armed, activity_seen, attempt)" in gps
    assert "s_gps_diag.backup_confirmations++" in gps
    assert "s_gps_diag.backup_terminal_failures++" in gps
    assert (
        "if (!gps_backup_reset_allowed(power_adc_read_vSTOR_mv())) { break; }"
        in gps
    ), "low reserve must suppress expensive backup recovery resets"

    assert "gps_quiesced = gps_ublox_sleep();" in main_source
    assert (
        "if (!gps_attempted_this_cycle) { gps_quiesced = gps_ublox_sleep(); }"
        in main_source
    ), "normal acquisition path must not execute a second recovery call in one cycle"
    assert "!gps_attempted_this_cycle || !gps_quiesced" not in main_source
    assert (
        "sleep_ms = (uint32_t)GPS_BACKUP_RETRY_SLEEP_MS;" in main_source
    )
    assert main_source.count(
        "gps_quiesced && !s_optical_quiescence_fault && !burst_mode && "
        "!power_manager_freefall_pending()"
    ) >= 2, "optional CTT/mesh windows must stay closed after terminal failure"
    assert "if (!gps_quiesced || s_optical_quiescence_fault)" in main_source, (
        "optional CTT/B2B uplinks must stay queued after terminal failure"
    )
    print("PASS: GNSS standby is independently confirmed and fails closed")


if __name__ == "__main__":
    main()
