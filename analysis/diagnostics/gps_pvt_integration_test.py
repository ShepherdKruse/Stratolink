#!/usr/bin/env python3
"""Pin the production wiring from a fresh NAV-PVT to the range gate."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "firmware/src/gps_ublox.cpp"


def main() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    gate = text.index("if (gps_pvt_to_wire_fix(&pvt, &wire))")
    accepted = text.index("s_gps_diag.accepted_fixes++", gate)
    copied = text.index("last_fix.lat_e7 = wire.lat_e7", gate)
    rejected = text.index("s_gps_diag.rejected_value_fixes++", gate)

    assert gate < copied < accepted < rejected
    assert "last_fix.lat_e7     = gnss.getLatitude()" not in text
    assert "last_fix.speed_cm_s = (uint16_t)(gnss.getGroundSpeed() / 10)" not in text
    assert "lorawan_b2b_set_local_crumb" not in text
    print(
        "PASS: fresh PVT fields cross the value gate before acceptance or "
        "downstream exposure"
    )


if __name__ == "__main__":
    main()
