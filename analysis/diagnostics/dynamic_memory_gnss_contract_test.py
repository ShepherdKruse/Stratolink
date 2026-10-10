#!/usr/bin/env python3
"""Check legacy and supervised GNSS source/ELF memory contracts, no build/target."""

from pathlib import Path

from dynamic_memory_audit import gnss_instance_contract


def main() -> None:
    gps = (Path(__file__).resolve().parents[2] / "firmware/src/gps_ublox.cpp").read_text()
    nm = "20000458 00000260 b gnss\n"
    legacy = "static SFE_UBLOX_GNSS_SERIAL gnss;"
    assert gnss_instance_contract(legacy, nm) == {
        "declaration": "legacy_serial", "static_object_bytes": 608,
        "subclass_adds_heap_allocations": False,
    }
    assert gnss_instance_contract(gps, nm) == {
        "declaration": "supervised_serial_subclass", "static_object_bytes": 608,
        "subclass_adds_heap_allocations": False,
    }
    for changed, symbols in (
        (gps.replace("using GpsGnssBase = SFE_UBLOX_GNSS_SERIAL;",
                     "using GpsGnssBase = SFE_UBLOX_GNSS;", 1), nm),
        (gps.replace("class GpsGnss : public GpsGnssBase {",
                     "class GpsGnss : public GpsGnssBase {\n    int extra;", 1), nm),
        (gps.replace("return packetCfg;", "new uint8_t[300]; return packetCfg;", 1), nm),
        (gps.replace("return currentSentence == SFE_UBLOX_SENTENCE_TYPE_NONE;",
                     "new uint8_t[1]; return currentSentence == SFE_UBLOX_SENTENCE_TYPE_NONE;", 1), nm),
        (gps.replace("static GpsGnss gnss;", "static GpsGnss* gnss;", 1), nm),
        (gps, nm.replace("00000260", "00000264")),
        (legacy, nm.replace("00000260", "00000264")),
        (gps, ""),
    ):
        try:
            gnss_instance_contract(changed, symbols)
        except RuntimeError:
            pass
        else:
            raise AssertionError("changed GNSS allocation/layout contract accepted")
    print("PASS: legacy/subclass GNSS source contracts and exact ELF size; 8 negative controls")


if __name__ == "__main__":
    main()
