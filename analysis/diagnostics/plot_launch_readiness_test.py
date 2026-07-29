#!/usr/bin/env python3
"""Fail closed when the readiness matrix and visualization drift apart."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import tempfile

import plot_launch_readiness as readiness


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="stratolink-readiness-plot-") as raw:
        output = Path(raw) / "readiness.png"
        output.write_bytes(b"preserved")
        try:
            readiness.output_paths(output)
        except SystemExit as error:
            assert "refusing to overwrite" in str(error)
        else:
            raise AssertionError("readiness plot accepted an existing output")
        assert output.read_bytes() == b"preserved"

    rows = readiness.parse_matrix(readiness.DEFAULT_MATRIX)
    claims = [claim for claim, _ in rows]
    expected = set().union(*readiness.DOMAINS.values())
    actual = set(claims)

    assert len(claims) == len(actual), "readiness matrix contains duplicate claims"
    assert actual == expected, (
        f"readiness map drift: missing={sorted(expected - actual)}, "
        f"extra={sorted(actual - expected)}"
    )

    categories = Counter()
    for claim, status in rows:
        readiness.domain_for(claim)
        categories[readiness.category(status)] += 1

    assert sum(categories.values()) == len(rows)
    assert set(categories) == {
        "Proven (scoped)",
        "Partial / modeled / configured",
        "Blocked",
    }
    assert readiness.category("NOT FROZEN / DO NOT FLASH") == "Blocked"
    print(
        "PASS: all readiness claims are uniquely mapped and every status is "
        "fail-closed categorized"
    )


if __name__ == "__main__":
    main()
