"""Execute the current C++ region manager for analysis/visualization inputs."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]

HELPER = r"""
#include "region_manager.h"
#include <cstdint>
#include <cstdio>

int main() {
    std::int32_t lat = 0;
    std::int32_t lon = 0;
    while (std::scanf("%d %d", &lat, &lon) == 2) {
        std::printf("%d\n", static_cast<int>(region_for_latlon(lat, lon)));
    }
    return 0;
}
"""


REGION_NAMES = {
    0: "US915",
    1: "EU868",
    2: "AS923",
    3: "AU915",
    4: "SILENT",
}


def compiled_regions(pairs: Iterable[tuple[int, int]]) -> list[int]:
    values = list(pairs)
    compiler = shutil.which(os.environ.get("CXX", "c++"))
    if compiler is None:
        raise RuntimeError("C++ compiler not found")
    stdin = "".join(f"{lat} {lon}\n" for lat, lon in values)
    with tempfile.TemporaryDirectory(prefix="stratolink-region-model-") as raw:
        build = Path(raw)
        helper = build / "region_model.cpp"
        binary = build / "region_model"
        helper.write_text(HELPER, encoding="utf-8")
        compiled = subprocess.run(
            [
                compiler,
                "-std=c++17",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-pedantic",
                "-I",
                str(ROOT / "firmware/include"),
                str(helper),
                str(ROOT / "firmware/src/region_manager.cpp"),
                "-o",
                str(binary),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if compiled.returncode != 0:
            raise RuntimeError(compiled.stdout + compiled.stderr)
        replay = subprocess.run(
            [str(binary)],
            input=stdin,
            text=True,
            capture_output=True,
            check=False,
        )
        if replay.returncode != 0:
            raise RuntimeError(replay.stdout + replay.stderr)
    result = [int(value) for value in replay.stdout.splitlines()]
    if len(result) != len(values):
        raise RuntimeError("compiled region model returned the wrong row count")
    unknown = sorted(set(result) - set(REGION_NAMES))
    if unknown:
        raise RuntimeError(f"compiled region model returned unknown IDs: {unknown}")
    return result
