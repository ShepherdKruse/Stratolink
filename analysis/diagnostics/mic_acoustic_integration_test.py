#!/usr/bin/env python3
"""Pin production acoustic capture observability and fail-safe arithmetic."""

from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
HEADER = ROOT / "firmware/include/mic_acoustic.h"
SOURCE = ROOT / "firmware/src/mic_acoustic.cpp"
GENERATOR = ROOT / "analysis/diagnostics/generate_flight_hil.py"
DECODER = ROOT / "analysis/diagnostics/decode_flight_state.py"


def compact(path: Path) -> str:
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


def main() -> None:
    header = compact(HEADER)
    source = compact(SOURCE)
    generator = compact(GENERATOR)
    decoder = compact(DECODER)

    for field in (
        "attempts",
        "captures",
        "capture_failures",
        "events",
        "last_variance_x16",
        "noise_floor_x16",
    ):
        assert f"uint32_t {field};" in header
        assert f'"{field}"' in decoder
    assert "static volatile mic_acoustic_diag_t s_mic_diag = {};" in source
    assert '"s_mic_diag"' in generator
    assert "s_mic_diag.capture_failures++;" in source
    assert "s_mic_diag.captures++;" in source
    assert "s_mic_diag.events++;" in source
    assert "(uint64_t)noise_floor_sq * THRESHOLD_MULT_SQ" in source
    assert "(uint64_t)noise_floor_sq * 2u" in source
    print("PASS: acoustic capture diagnostics and overflow-safe thresholds wired")


if __name__ == "__main__":
    main()
