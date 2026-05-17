"""Tests for the HRRR client — path generation, idx parsing, byte-range computation.

Network-dependent paths (download + cfgrib open) are exercised by the
out-of-band script ``scripts/verify_phase2_hrrr.py``; this file is
deterministic and runs offline.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from predictor.weather.hrrr_client import (
    EXTENDED_CYCLES_UTC,
    HRRRCycle,
    _IdxRecord,
    _compute_byte_ranges,
    parse_idx,
    select_uv_pressure_records,
)


def _utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def test_cycle_requires_utc():
    with pytest.raises(ValueError, match="UTC"):
        HRRRCycle(cycle_dt=datetime(2026, 5, 17, 12, 0))  # naive


def test_cycle_requires_hour_alignment():
    with pytest.raises(ValueError, match="hour-aligned"):
        HRRRCycle(cycle_dt=_utc(2026, 5, 17, 12, 30))


def test_cycle_rejects_unknown_domain():
    with pytest.raises(ValueError, match="domain"):
        HRRRCycle(cycle_dt=_utc(2026, 5, 17, 12), domain="europe")


def test_s3_prefix_and_key_format():
    cycle = HRRRCycle(cycle_dt=_utc(2026, 5, 17, 12))
    assert cycle.s3_prefix == "hrrr.20260517/conus/"
    # key() inserts the literal "f" between product and forecast hour
    assert cycle.key("wrfprs", 0) == "hrrr.20260517/conus/hrrr.t12z.wrfprsf00.grib2"
    assert cycle.key("wrfprs", 1).endswith("wrfprsf01.grib2")
    assert cycle.url("wrfprs", 0).startswith("https://noaa-hrrr-bdp-pds.s3.amazonaws.com/")


def test_max_fxx_depends_on_cycle_hour():
    for h in EXTENDED_CYCLES_UTC:
        assert HRRRCycle(cycle_dt=_utc(2026, 5, 17, h)).max_fxx() == 48
    for h in (1, 5, 11, 23):
        assert HRRRCycle(cycle_dt=_utc(2026, 5, 17, h)).max_fxx() == 18


def test_alaska_domain_path():
    cycle = HRRRCycle(cycle_dt=_utc(2026, 5, 17, 0), domain="alaska")
    assert cycle.s3_prefix == "hrrr.20260517/alaska/"


SAMPLE_IDX = """\
1:0:d=2026051712:TMP:500 mb:anl:
2:1234567:d=2026051712:UGRD:500 mb:anl:
3:2345678:d=2026051712:VGRD:500 mb:anl:
4:3456789:d=2026051712:UGRD:850 mb:anl:
5:4567890:d=2026051712:VGRD:850 mb:anl:
6:5678901:d=2026051712:UGRD:10 m above ground:anl:
7:6789012:d=2026051712:VGRD:10 m above ground:anl:
8:7890123:d=2026051712:HGT:500 mb:anl:
"""


def test_parse_idx_skips_blank_and_malformed_lines():
    text = SAMPLE_IDX + "\n\nthis is not a record\n"
    records = parse_idx(text)
    assert len(records) == 8
    assert records[0].short_name == "TMP"
    assert records[1].byte_start == 1234567


def test_select_uv_pressure_records_filters_correctly():
    records = parse_idx(SAMPLE_IDX)
    selected = select_uv_pressure_records(records)
    # Only UGRD/VGRD on mb levels — surface-AGL and TMP/HGT are dropped
    short_names = {r.short_name for r in selected}
    levels = {r.level for r in selected}
    assert short_names == {"UGRD", "VGRD"}
    assert "500 mb" in levels
    assert "850 mb" in levels
    assert "10 m above ground" not in levels
    assert len(selected) == 4


def test_select_uv_pressure_records_restricts_to_levels():
    records = parse_idx(SAMPLE_IDX)
    selected = select_uv_pressure_records(records, levels_mb=[500])
    assert len(selected) == 2
    assert all(r.level == "500 mb" for r in selected)


def test_select_records_sorted_by_offset():
    records = parse_idx(SAMPLE_IDX)
    selected = select_uv_pressure_records(records)
    offsets = [r.byte_start for r in selected]
    assert offsets == sorted(offsets), "selected records must be sorted by offset"


def test_byte_ranges_use_next_message_as_upper_bound():
    records = parse_idx(SAMPLE_IDX)
    selected = select_uv_pressure_records(records, levels_mb=[500])
    ranges = _compute_byte_ranges(selected, records, file_length=9000000)
    # 500 mb UGRD is msg 2 at offset 1234567; next msg is 3 at 2345678
    # So range should be 1234567 .. 2345677 (inclusive)
    assert ranges[0] == (1234567, 2345677)
    # 500 mb VGRD is msg 3 at offset 2345678; next msg is 4 at 3456789
    assert ranges[1] == (2345678, 3456788)


def test_byte_ranges_use_file_length_for_last_message():
    records = parse_idx(SAMPLE_IDX)
    # Take only the last UV record (which is msg 7 in this fixture)
    last = [r for r in select_uv_pressure_records(records) if r.msg_no == 5][0]
    # Make a tiny idx where this is the last message
    truncated = [r for r in records if r.byte_start <= last.byte_start]
    ranges = _compute_byte_ranges([last], truncated, file_length=4_700_000)
    assert ranges[0][0] == last.byte_start
    assert ranges[0][1] == 4_700_000 - 1  # inclusive end


def test_byte_ranges_handle_missing_file_length():
    """When HEAD fails to return Content-Length we fall back to an open range."""
    records = parse_idx(SAMPLE_IDX)
    last = [r for r in records if r.msg_no == 8][0]
    ranges = _compute_byte_ranges([last], records, file_length=None)
    start, end = ranges[0]
    assert start == last.byte_start
    assert end - start > 0
