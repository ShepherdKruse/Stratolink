#!/usr/bin/env python3
"""Pin the flight loop's atomic fresh-fix/NOGPS telemetry contract."""

from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "firmware/src/main.cpp"
GPS = ROOT / "firmware/src/gps_ublox.cpp"


GPS_FIELDS = (
    "lat_e7",
    "lon_e7",
    "altitude_m",
    "gps_speed_cm_s",
    "gps_heading_cd",
    "gps_satellites",
)


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def main() -> None:
    raw_main = MAIN.read_text(encoding="utf-8")
    main_source = compact(raw_main)
    gps_source = compact(GPS.read_text(encoding="utf-8"))

    # Value-initialize the complete packet every cycle. The failed acquisition
    # branch must inherit these zeroes rather than a prior gps_fix_t cache.
    packet_init = main_source.index(
        "telemetry_input_t ti; telemetry_input_init(&ti);"
    )
    acquisition = main_source.index(
        "if (gps_ublox_get_fix(&last_gps_fix, gps_timeout_ms))",
        packet_init,
    )
    success_end = main_source.index(
        "/* No fresh fix this cycle -> GPS fields stay zero (NOGPS).",
        acquisition,
    )
    pack = main_source.index("telemetry_pack(&ti, tx_payload);", success_end)
    success_branch = main_source[acquisition:success_end]

    expected_assignments = {
        "lat_e7": "ti.lat_e7 = last_gps_fix.lat_e7;",
        "lon_e7": "ti.lon_e7 = last_gps_fix.lon_e7;",
        "altitude_m": "ti.altitude_m = last_gps_fix.altitude_m;",
        "gps_speed_cm_s": "ti.gps_speed_cm_s = last_gps_fix.speed_cm_s;",
        "gps_heading_cd": "ti.gps_heading_cd = last_gps_fix.heading_cd;",
        "gps_satellites": "ti.gps_satellites = last_gps_fix.satellites;",
    }
    for field in GPS_FIELDS:
        assignment = expected_assignments[field]
        assert assignment in success_branch
        # No fallback or later mutation may populate a partially stale packet.
        assert main_source.count(f"ti.{field} =") == 1

    assert packet_init < acquisition < success_end < pack
    assert "gps_ublox_get_last_fix(" not in main_source
    assert "else { ti.lat_e7" not in success_branch

    # B2B position originates only inside the same accepted-fix branch.
    crumb = success_branch.index("lorawan_b2b_set_local_crumb(")
    assert crumb > success_branch.index(
        "ti.gps_satellites = last_gps_fix.satellites;"
    )
    assert main_source.count("lorawan_b2b_set_local_crumb(") == 1

    # Every non-null false-return exit from the real GNSS implementation has
    # crossed all three cache/output invalidations. Power skips use their own
    # explicit invalidation entry point, called by the flight loop.
    get_fix_start = gps_source.index("bool gps_ublox_get_fix(")
    get_fix_end = gps_source.index("void gps_ublox_note_power_skip", get_fix_start)
    get_fix = gps_source[get_fix_start:get_fix_end]
    false_returns = [match.start() for match in re.finditer("return false;", get_fix)]
    assert len(false_returns) == 7
    invalidations = (
        "last_fix.valid = false;",
        "fix->valid = false;",
        "fix->satellites = 0;",
    )
    # The four early branches each own a fresh invalidation block after the
    # preceding return. The final two returns deliberately share the one
    # common post-poll invalidation block.
    for index in range(1, 6):
        for invalidation in invalidations:
            assert get_fix.rfind(
                invalidation, false_returns[index - 1], false_returns[index]
            ) >= 0
    for invalidation in invalidations:
        common = get_fix.rfind(invalidation, 0, false_returns[-1])
        assert false_returns[-3] < common < false_returns[-2]
    assert "else { gps_ublox_note_power_skip(); }" in main_source
    assert (
        "void gps_ublox_note_power_skip(void) { "
        "gps_freshness_reset(&pvt_freshness); last_fix.valid = false; }"
        in gps_source
    )

    print(
        "PASS: every failed acquisition remains one atomic all-zero NOGPS "
        "packet, and B2B cannot originate a cached position"
    )


if __name__ == "__main__":
    main()
