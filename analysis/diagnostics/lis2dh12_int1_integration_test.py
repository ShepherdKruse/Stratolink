#!/usr/bin/env python3
"""Pin the aggregate LIS2DH12 freefall-source decode into the real driver."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DRIVER = (ROOT / "firmware/src/sensor_lis2dh12.cpp").read_text(encoding="utf-8")
HELPER = (ROOT / "firmware/include/lis2dh12_conversion.h").read_text(encoding="utf-8")
HOST = (ROOT / "firmware/test/test_lis2dh12_conversion.cpp").read_text(encoding="utf-8")


def main() -> None:
    assert "#define LIS2DH12_INT1_CFG_AOI  (1 << 7)" in DRIVER
    assert "LIS2DH12_INT1_CFG_XLIE" in DRIVER
    assert "LIS2DH12_INT1_CFG_YLIE" in DRIVER
    assert "LIS2DH12_INT1_CFG_ZLIE" in DRIVER
    assert "return lis2dh12_int1_active((uint8_t)Wire.read());" in DRIVER
    assert "(Wire.read() & 0x3F) != 0" not in DRIVER
    assert "return (source & 0x40u) != 0u;" in HELPER
    assert "return sample_ok && magnitude_cleared;" in HELPER
    assert "lis2dh12_freefall_is_cleared(sample_ok, cleared)" in DRIVER
    assert "!sensor_lis2dh12_get_freefall_cleared(&cleared) || cleared" not in DRIVER
    for source in ("0x01", "0x15", "0x3F"):
        assert f"!lis2dh12_int1_active({source})" in HOST
    for source in ("0x40", "0x55", "0xFF"):
        assert f"lis2dh12_int1_active({source})" in HOST
    for vector in (
        "false, false",
        "false, true",
        "true, false",
    ):
        assert f"!lis2dh12_freefall_is_cleared({vector})" in HOST
    assert "lis2dh12_freefall_is_cleared(true, true)" in HOST
    print(
        "PASS: LIS2DH12 AOI freefall reads aggregate IA only and an "
        "unavailable sample cannot clear bounded recovery"
    )


if __name__ == "__main__":
    main()
