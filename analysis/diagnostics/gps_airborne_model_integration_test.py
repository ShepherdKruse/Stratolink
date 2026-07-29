#!/usr/bin/env python3
"""Lock fail-closed AIRBORNE_4G enforcement into the production GNSS path."""

from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
GPS = ROOT / "firmware/src/gps_ublox.cpp"
MAIN = ROOT / "firmware/src/main.cpp"


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def main() -> None:
    gps = compact(GPS.read_text(encoding="utf-8"))
    main_source = compact(MAIN.read_text(encoding="utf-8"))
    config = compact(
        (ROOT / "firmware/include/config.h").read_text(encoding="utf-8")
    )

    # Initialization is successful only when the model is read back, and the
    # old redundant setup call cannot hide gps_ublox_init()'s result.
    assert "bool dyn_model_ok = ok && gps_ublox_set_airborne_4g();" in gps
    assert "return ok && dyn_model_ok;" in gps
    assert "gps_ublox_set_airborne_4g()" not in main_source
    assert "#define GPS_DYNMODEL_MAX_WAIT_MS 300u" in config
    assert "#define GPS_BEGIN_MAX_WAIT_MS 1100u" in config
    assert gps.count("GPS_DYNMODEL_MAX_WAIT_MS") == 4
    assert "VAL_LAYER_RAM_BBR, GPS_DYNMODEL_MAX_WAIT_MS" in gps

    reset_start = gps.index("static bool gps_ublox_reset(void)")
    get_fix_start = gps.index("bool gps_ublox_get_fix(", reset_start)
    reset = gps[reset_start:get_fix_start]
    assert (
        "bool begin_ok = gnss.begin(GPS_SERIAL, GPS_BEGIN_MAX_WAIT_MS);"
        in reset
    )
    assert "bool dyn_model_ok = begin_ok && gps_ublox_set_airborne_4g();" in reset
    assert "return begin_ok && dyn_model_ok;" in reset

    get_fix_end = gps.index("void gps_ublox_note_power_skip", get_fix_start)
    get_fix = gps[get_fix_start:get_fix_end]
    model_gate = get_fix.index("if (!gps_ublox_set_airborne_4g())")
    post_retry_power_gate = get_fix.index(
        "if (power_adc_read_vSTOR_mv() < GPS_ACQ_FLOOR_MV)", model_gate
    )
    reset_retry = get_fix.index("if (!gps_ublox_reset())", model_gate)
    terminal = get_fix.index("s_gps_diag.dyn_model_terminal_failures++", reset_retry)
    pvt_poll = get_fix.index("while ((int32_t)(deadline - millis()) > 0)")
    position_read = get_fix.index("gnss.getLatitude()", pvt_poll)
    assert (
        model_gate
        < post_retry_power_gate
        < reset_retry
        < terminal
        < pvt_poll
        < position_read
    )
    assert "fix->valid = false; fix->satellites = 0; return false;" in get_fix[
        terminal:pvt_poll
    ]

    # The same-cycle frozen/silent recovery must also stop acquisition if its
    # reset cannot re-prove the model; it may never fall through to a PVT read
    # in an unknown model.
    assert get_fix.count("s_gps_diag.dyn_model_terminal_failures++") == 2
    assert "bool dyn_model_aborted = false;" in get_fix
    assert "bool model_reset_performed = false;" in get_fix
    assert "model_reset_performed = true;" in get_fix
    assert "bool inline_reset_attempted = model_reset_performed;" in get_fix
    assert "gps_recovery_due(epoch_anchor_available, now," in get_fix
    assert "gps_recovery_due(itow_advanced" not in get_fix
    assert "gps_stale_ladder_step(module_responded && itow_advanced," in get_fix
    assert "inline_reset_attempted," in get_fix
    assert "dyn_model_aborted = true; break;" in get_fix
    assert "power_aborted || mission_aborted || dyn_model_aborted" in get_fix

    print(
        "PASS: AIRBORNE_4G is read-back enforced before PVT acceptance, with "
        "one bounded RESET_N recovery and a terminal fail-closed path"
    )


if __name__ == "__main__":
    main()
