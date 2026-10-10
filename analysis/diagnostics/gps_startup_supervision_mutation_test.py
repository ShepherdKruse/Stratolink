#!/usr/bin/env python3
"""Compile guard-removal mutants against the real-parser startup regression.

No production file is edited. Each mutant must fail its named behavioral case,
not compilation or a sanitizer check, so a vacuous fixture cannot qualify it.
"""

import os
from pathlib import Path
import subprocess
import tempfile

import gps_startup_supervision_test as fixture


MUTANTS = (
    ("key_match_removed", "if (returned_key == key)", "if (true)", "wrong_key"),
    ("entry_deadline_extended",
     "uint32_t deadline = entered_ms + timeout_ms;",
     "uint32_t deadline = entered_ms + timeout_ms + 5000u;", "deadline"),
    ("read_first_bypassed", "if (model == GPS_DYNMODEL_AIRBORNE_4G) return true;",
     "if (false) return true;", "healthy"),
    ("expired_response_not_cancelled",
     "    (void)gps_startup_allowed(context);",
     "    /* authority not observed */", "connection_deadline"),
    ("parser_slice_unbounded", "gps_gnss_stream.begin_read_slice(5u, 16u);",
     "gps_gnss_stream.begin_read_slice(10000u, 65535u);", "rx_load"),
)


def main():
    root, lib = fixture.ROOT, fixture.LIB
    source_path = root / "firmware/src/gps_ublox.cpp"
    source = source_path.read_text()
    with tempfile.TemporaryDirectory(prefix="gps-startup-mutants-") as name:
        for label, before, after, case in MUTANTS:
            assert before in source, label
            build = Path(name) / label
            build.mkdir()
            mutant = source.replace(before, after)
            for filename, contents in (("Arduino.h", fixture.ARDUINO),
                                       ("Wire.h", fixture.fixture.WIRE),
                                       ("SPI.h", fixture.fixture.SPI),
                                       ("gps_ublox.cpp", mutant),
                                       ("test.cpp", fixture.TEST)):
                (build / filename).write_text(contents)
            binary = build / "test"
            subprocess.run([
                os.environ.get("CXX", "c++"), "-std=c++17", "-Wno-vla-cxx-extension",
                "-fcheck-new", "-Wno-new-returns-null",
                "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-g",
                "-I", str(build), "-I", str(root / "firmware/include"),
                "-I", str(root / "firmware/src"), "-I", str(lib),
                str(lib / "u-blox_GNSS.cpp"), str(lib / "sfe_bus.cpp"), str(build / "test.cpp"),
                *(str(root / f"firmware/src/{n}.cpp") for n in
                  ("gps_freshness", "gps_pvt_validation", "gps_backup_policy")),
                "-o", str(binary)], check=True, timeout=60)
            result = subprocess.run([str(binary), case], capture_output=True, text=True,
                                    timeout=20, env=dict(os.environ, ASAN_OPTIONS="detect_leaks=0",
                                                         UBSAN_OPTIONS="halt_on_error=1"))
            assert result.returncode == 1 and not result.stderr, (label, result)
            assert f"[FAIL] {case} " in result.stdout, (label, result.stdout)
            print(f"PASS: {label} rejected: {result.stdout.strip()}")
    assert source_path.read_text() == source
    print(f"PASS: {len(MUTANTS)} compiled startup mutants; production unchanged")


if __name__ == "__main__":
    main()
