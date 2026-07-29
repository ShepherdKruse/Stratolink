#!/usr/bin/env python3
"""Prove the embedded geofence diagnostic agrees with production C++."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import re

from compiled_region import REGION_NAMES, compiled_regions


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "firmware/src/main_region_test.cpp"
NAME_TO_ID = {name: value for value, name in REGION_NAMES.items()}


def e7(token: str) -> int:
    token = token.strip()
    match = re.fullmatch(r"E7\(([-+]?\d+(?:\.\d+)?)\)", token)
    if match:
        return int(Decimal(match.group(1)) * 10_000_000)
    return int(token)


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    block = re.search(
        r"static const GeoCase GEO_CASES\[\]\s*=\s*\{(.*?)\n\};",
        source,
        re.DOTALL,
    )
    assert block, "embedded GEO_CASES table not found"
    rows = re.findall(
        r'\{\s*"([^"]+)"\s*,\s*([^,]+)\s*,\s*([^,]+)\s*,\s*'
        r"LORA_REGION_([A-Z0-9]+)\s*\}",
        block.group(1),
    )
    assert len(rows) >= 15, "embedded geofence table unexpectedly shrank"

    pairs = [(e7(lat), e7(lon)) for _, lat, lon, _ in rows]
    actual = compiled_regions(pairs)
    failures = []
    for (name, _, _, expected_name), actual_id in zip(rows, actual):
        expected_id = NAME_TO_ID[expected_name]
        if actual_id != expected_id:
            failures.append(
                f"{name}: embedded expects {expected_name}, production returns "
                f"{REGION_NAMES[actual_id]}"
            )
    assert not failures, "\n".join(failures)
    print(
        f"PASS: all {len(rows)} embedded region-diagnostic expectations agree "
        "with the current compiled production geofence"
    )


if __name__ == "__main__":
    main()
