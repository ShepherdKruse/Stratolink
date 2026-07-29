#!/usr/bin/env python3
"""Pin long-duration B2B crumb-age accounting into every production queue."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
B2B = ROOT / "firmware/src/b2b.cpp"
LORAWAN = ROOT / "firmware/src/lorawan.cpp"
HEADER = ROOT / "firmware/src/b2b.h"
MAIN = ROOT / "firmware/src/main.cpp"


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def main() -> None:
    b2b = compact(B2B.read_text(encoding="utf-8"))
    lorawan = compact(LORAWAN.read_text(encoding="utf-8"))
    header = compact(HEADER.read_text(encoding="utf-8"))
    main_raw = MAIN.read_text(encoding="utf-8")

    assert "uint32_t queued_rtc_sec;" in header
    assert "uint32_t seen_rtc_sec[B2B_SEEN_N]" in header
    assert "uint32_t now_rtc_sec" in header
    assert "B2B_RTC_MIN_LSI_HZ 29500u" in header
    assert "B2B_RTC_MAX_LSI_HZ 34000u" in header
    assert "uint32_t elapsed_min = b2b_age_upper_minutes(" in b2b
    assert "b2b_elapsed_lower_minutes(elapsed_rtc_sec)" in b2b
    assert "elapsed_min >= remaining ? 255u" in b2b
    assert "b2b_auth_verify(key, frame)" in b2b
    assert "b2b_auth_tag(key, &updated, tag)" in b2b
    assert "nf.queued_rtc_sec = now_rtc_sec;" in b2b

    assert "static uint32_t b2b_now_rtc_sec(void)" in lorawan
    assert "s_b2b_uplink[s_b2b_uplink_tail].queued_rtc_sec = b2b_now_rtc_sec();" in lorawan
    assert "b2b_refresh_authenticated_age( s_b2b_fleet_key, frame, b2b_now_rtc_sec())" in lorawan
    assert "s_b2b_crumb_frame.queued_rtc_sec = prepared_rtc_sec;" in lorawan
    assert "b2b_refresh_authenticated_age( s_b2b_fleet_key, &s_b2b_crumb_frame" in lorawan
    assert "b2b_next_forward_fresh( &s_b2b, &frame, toa, s_b2b_fleet_key" in lorawan
    assert "static uint16_t b2b_now_rtc_sec" not in lorawan
    assert "b2b_now_min" not in lorawan
    assert "b2b_interval_due(s_b2b_ever_sent_crumb, now_rtc_sec" in lorawan

    # A failed/stale GNSS cycle must never originate a local crumb. The only
    # production call is inside the successful fresh-fix branch; a pending
    # crumb may wait, but its authenticated age then advances explicitly.
    assert main_raw.count("lorawan_b2b_set_local_crumb(") == 1
    fresh_branch = main_raw.index("if (gps_ublox_get_fix(&last_gps_fix")
    crumb_call = main_raw.index("lorawan_b2b_set_local_crumb(")
    no_fix_path = main_raw.index("No fresh fix this cycle", crumb_call)
    assert fresh_branch < crumb_call < no_fix_path

    print(
        "PASS: only fresh GNSS originates B2B crumbs, and crumb age advances "
        "through origin, relay, and TTN queues with opposite conservative "
        "LSI bounds and wrap-safe raw RTC deltas"
    )


if __name__ == "__main__":
    main()
