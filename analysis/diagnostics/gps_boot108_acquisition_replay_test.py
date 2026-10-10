#!/usr/bin/env python3
"""Replay scalar boot-108 observations through the current acquisition policy.

Real driver/freshness/value/backup policies, fake GNSS and clock boundaries.
Absent position/velocity fields are synthetic, configuration replies are ideal
packet-shaped responses checked by production (not the pinned parser), and the
latest observation is held between timestamps. This is not a UART replay,
uninstrumented TTFF measurement, RF test, or physical timing/energy proof.
The source capture used a diagnostic 180s override and perturbed MCU timing.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

import gps_acquisition_runtime_test as harness


FIXTURE = harness.ROOT / "analysis/diagnostics/fixtures/gps_acquisition_boot108_pvt.json"
FIXTURE_SHA256 = "b6542ed6a2c606ff9e476fa7394f32479403183cd6a68b567fd62cdde891ff75"
CAPTURE_SHA256 = "b24659ad70b386119ff3d6804c5de6941792d90a595b1c6de7551788b1cd105f"
FIELDS = ["acquisition_elapsed_ms", "itow", "valid", "fixType", "flags", "satellites"]

TEST = harness.TEST.split("int main() {", 1)[0] + r"""
int main() {
    reset_case(COLD);
    gps_fix_t fix = previously_valid();
    check("30s rejects advancing no-fix trace without reset",
        !gps_ublox_get_fix(&fix, 30000u) && !fix.valid &&
        fix.satellites == 0u && !last_fix.valid &&
        s_gps_diag.accepted_fixes == 0u && s_gps_diag.no_fresh_cycles == 1u &&
        no_reset() && fake_millis >= 30000u && fake_millis < 31000u);

    // Both budgets end after a captured 3D/4-SV row, before observed fixOK.
    for (uint32_t budget : {109500u, 111800u}) {
        reset_case(COLD);
        fix = previously_valid();
        check("3D without fixOK remains unusable",
            !gps_ublox_get_fix(&fix, budget) && !fix.valid &&
            !last_fix.valid && fix.satellites == 0u &&
            current.fix_type == 3u && current.flags == 0u &&
            s_gps_diag.accepted_fixes == 0u && no_reset() &&
            fake_millis >= budget && fake_millis < 112185u);
    }

    reset_case(COLD);
    check("180s accepts only the observed 112185ms fixOK row",
        gps_ublox_get_fix(&fix, 180000u) && expected_position(fix) &&
        current.elapsed == 112185u && current.itow == 235426000u &&
        current.fix_type == 3u && current.flags == 1u &&
        s_gps_diag.accepted_fixes == 1u && s_gps_diag.no_fresh_cycles == 0u &&
        no_reset() && fake_millis >= 112185u && fake_millis < 112400u);
    std::printf("REPLAY_ACCEPT observed_elapsed_ms=%u host_tick_ms=%u\n",
                current.elapsed, fake_millis);
    return failures ? 1 : 0;
}
"""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-capture", type=Path,
                        help="Optionally verify all portable rows against the original capture")
    args = parser.parse_args()
    assert sha256(FIXTURE) == FIXTURE_SHA256
    fixture = json.loads(FIXTURE.read_text())
    assert fixture["source_capture_sha256"] == CAPTURE_SHA256
    assert fixture["fields"] == FIELDS
    rows = fixture["frames"]
    assert len(rows) == 139
    assert all(len(row) == 6 and all(type(v) is int and v >= 0 for v in row)
               for row in rows)
    assert all(a[0] < b[0] for a, b in zip(rows, rows[1:]))
    assert rows[0] == [618, 3000, 240, 0, 0, 0]
    assert next(row for row in rows if row[3] == 3) == [109122, 235422000, 243, 3, 0, 4]
    assert [row for row in rows if row[4] & 1] == [[112185, 235426000, 243, 3, 1, 4]]
    if args.source_capture:
        assert sha256(args.source_capture) == CAPTURE_SHA256
        original = json.loads(args.source_capture.read_text())
        extracted = []
        for line in original["capture"]["lines"]:
            if line["text"].startswith("PVT_SNAPSHOT "):
                fields = dict(re.findall(r"(\w+)=(\d+)", line["text"]))
                extracted.append([int(fields[key]) for key in FIELDS])
        assert extracted == rows

    values = ",\n".join("    {" + ", ".join(f"{v}u" for v in row) + "}" for row in rows)
    frames = "\n".join(f"inline const Frame {name}[] = {{\n{values}\n}};"
                       for name in ("cold_frames", "warm_frames"))
    # Reuse the existing parametric compiler and doubles; do not edit its file.
    # Include fixType in the fake PVT too, though current production policy uses
    # the gnssFixOK flag and satellite threshold, not a fixType gate.
    harness.GNSS_PREFIX = harness.GNSS_PREFIX.replace(
        "uint8_t numSV;", "uint8_t numSV, fixType;")
    harness.GNSS = harness.GNSS.replace(
        "storage.data.numSV = current.satellites;",
        "storage.data.numSV = current.satellites;\n"
        "        storage.data.fixType = current.fix_type;")
    harness.TEST = TEST
    inputs = [harness.SOURCE, FIXTURE, Path(__file__).resolve(),
              Path(harness.__file__).resolve(), Path(harness.base.__file__).resolve(),
              harness.ROOT / "firmware/include/gps_bounded_stream.h"]
    inputs += [harness.ROOT / f"firmware/{folder}/{name}.{ext}"
               for name in ("gps_freshness", "gps_pvt_validation", "gps_backup_policy")
               for folder, ext in (("src", "cpp"), ("include", "h"))]
    before = {str(path.relative_to(harness.ROOT)): sha256(path) for path in inputs}
    source = harness.SOURCE.read_text()
    old, new, _ = harness.MUTATIONS["bypass-fixok"]
    assert source.count(old) == 1
    red = harness.run(source.replace(old, new, 1), frames)
    assert red.returncode == 1 and not red.stderr, red
    assert red.stdout.count("[FAIL] 3D without fixOK remains unusable:") == 2, red.stdout
    green = harness.run(source, frames)
    assert green.returncode == 0 and not green.stderr, green
    assert green.stdout.count("[PASS]") == 4, green.stdout
    assert before == {str(path.relative_to(harness.ROOT)): sha256(path) for path in inputs}
    if args.source_capture:
        assert sha256(args.source_capture) == CAPTURE_SHA256
    print(json.dumps({
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "passed": True, "cases_passed": 4, "compiled_mutants_rejected": 1,
        "source_capture_audit_passed": bool(args.source_capture),
        "source_capture_sha256": CAPTURE_SHA256, "inputs_sha256": before,
        "inputs_unchanged": True, "sanitizers": ["address", "undefined"],
        "green_output": green.stdout, "negative_control_output": red.stdout,
        "limitations": fixture["limitations"],
        "real_driver_policy_fake_gnss": True, "flight_qualification": False,
    }, indent=2))


if __name__ == "__main__":
    main()
