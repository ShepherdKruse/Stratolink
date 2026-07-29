#!/usr/bin/env python3
"""Test precursor-preservation preconditions without accessing hardware."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile

from evidence_provenance import record
from preserve_precursor import (
    commit_partial_create_once,
    file_record,
    require_flash_unchanged,
    run_jlink,
    validate_option_register,
)
from verify_flight_candidate import EXPECTED_BIN_SHA256, EXPECTED_ELF_SHA256


HERE = Path(__file__).resolve().parent


def run(
    prefix: Path,
    summary: Path,
    sensor: Path,
    candidate: Path,
    handoff: Path,
    pre_retry_flash: Path,
    evidence: dict[str, Path],
    jlink_serial: str = "802007563",
    engineering_acceptance: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [
            sys.executable,
            str(HERE / "preserve_precursor.py"),
            "--check-only",
            "--prefix",
            str(prefix),
            "--summary",
            str(summary),
            "--sensor-model",
            str(sensor),
            "--candidate-verification",
            str(candidate),
            "--handoff-power",
            str(handoff),
            "--pre-retry-flash",
            str(pre_retry_flash),
            "--expected-pre-retry-flash-sha256",
            hashlib.sha256(pre_retry_flash.read_bytes()).hexdigest(),
            "--primary-power",
            str(evidence["power"]),
            "--ttn",
            str(evidence["ttn"]),
            "--supabase",
            str(evidence["supabase"]),
            "--soak-plot",
            str(evidence["soak_plot"]),
            "--readiness-plot",
            str(evidence["readiness_plot"]),
            "--candidate-elf",
            str(evidence["elf"]),
            "--candidate-bin",
            str(evidence["bin"]),
            "--jlink-serial",
            jlink_serial,
        ]
    if engineering_acceptance is not None:
        command.extend(
            ["--engineering-acceptance", str(engineering_acceptance)]
        )
    return subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
    )


def main() -> None:
    bare = subprocess.run(
        [sys.executable, str(HERE / "preserve_precursor.py"), "--check-only"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert bare.returncode != 0
    assert "the following arguments are required" in bare.stderr

    with tempfile.TemporaryDirectory(prefix="stratolink-preserve-test-") as raw:
        root = Path(raw)
        partial = root / "atomic.bin.partial"
        destination = root / "atomic.bin"
        partial.write_bytes(b"new evidence")
        destination.write_bytes(b"old evidence")
        try:
            commit_partial_create_once(partial, destination, "test evidence")
        except SystemExit as error:
            assert "refusing to overwrite test evidence" in str(error)
        else:
            raise AssertionError("existing evidence was replaced")
        assert destination.read_bytes() == b"old evidence"
        assert partial.read_bytes() == b"new evidence"
        destination.unlink()
        commit_partial_create_once(partial, destination, "test evidence")
        assert destination.read_bytes() == b"new evidence"
        assert not partial.exists()
        summary = root / "summary.json"
        sensor = root / "sensor.json"
        candidate = root / "candidate.json"
        handoff = root / "handoff.jsonl"
        source = root / "source.log"
        evidence = {
            name: root / name
            for name in (
                "power",
                "ttn",
                "supabase",
                "soak_plot",
                "readiness_plot",
                "elf",
                "bin",
            )
        }
        for path in evidence.values():
            path.write_bytes(b"fixture\n")
        prefix = root / "precursor"
        pre_retry_flash = root / "pre-retry-flash.bin"
        pre_retry_flash.write_bytes(b"\xff" * (256 * 1024))
        post_soak_flash = root / "post-soak-flash.bin"
        post_soak_flash.write_bytes(pre_retry_flash.read_bytes())
        require_flash_unchanged(file_record(pre_retry_flash), post_soak_flash)
        optr = root / "optr.bin"
        optr.write_bytes((1 << 17).to_bytes(4, byteorder="little"))
        assert validate_option_register(optr)["iwdg_runs_in_stop"] is True
        optr.write_bytes((0).to_bytes(4, byteorder="little"))
        try:
            validate_option_register(optr)
        except SystemExit as error:
            assert "IWDG_STOP is clear" in str(error)
        else:
            raise AssertionError("STOP-frozen watchdog option unexpectedly passed")
        post_soak_flash.write_bytes(b"\x00" + post_soak_flash.read_bytes()[1:])
        try:
            require_flash_unchanged(
                file_record(pre_retry_flash), post_soak_flash
            )
        except SystemExit as error:
            assert "pre-retry/post-soak flash mismatch" in str(error)
        else:
            raise AssertionError("mutated post-soak flash unexpectedly passed")
        source.write_text("frozen evidence\n", encoding="utf-8")
        summary.write_text(
            json.dumps(
                {
                    "final_gate": {"passed": True},
                    "provenance": {"source": record(source)},
                }
            ),
            encoding="utf-8",
        )
        sensor.write_text(
            json.dumps(
                {
                    "passed": True,
                    "provenance": {"source": record(source)},
                }
            ),
            encoding="utf-8",
        )
        candidate.write_text(
            json.dumps(
                {
                    "passed": True,
                    "candidate": {
                        "elf_sha256": EXPECTED_ELF_SHA256,
                        "bin_sha256": EXPECTED_BIN_SHA256,
                    },
                    "provenance": {"source": record(source)},
                }
            ),
            encoding="utf-8",
        )
        now = datetime.now(timezone.utc)
        handoff.write_text(
            "".join(
                json.dumps(row) + "\n"
                for row in (
                    {
                        "utc": (now - timedelta(seconds=30)).isoformat(),
                        "event": "ppk2_power_on",
                        "source_mv": 4660,
                        "reconnects": 0,
                    },
                    {
                        "utc": now.isoformat(),
                        "event": "ppk2_power_heartbeat",
                        "source_mv": 4660,
                        "reconnects": 0,
                    },
                )
            ),
            encoding="utf-8",
        )

        ready = run(
            prefix, summary, sensor, candidate, handoff, pre_retry_flash,
            evidence,
        )
        assert ready.returncode == 0, ready.stdout + ready.stderr
        assert '"ready": true' in ready.stdout
        evidence["power"].unlink()
        missing_evidence = run(
            prefix,
            summary,
            sensor,
            candidate,
            handoff,
            pre_retry_flash,
            evidence,
        )
        assert missing_evidence.returncode != 0
        assert "evidence bundle inputs are missing" in missing_evidence.stderr
        evidence["power"].write_bytes(b"fixture\n")

        collision = prefix.with_name(prefix.name + "_flash.bin")
        collision.write_bytes(b"do not overwrite")
        refused = run(
            prefix, summary, sensor, candidate, handoff, pre_retry_flash,
            evidence,
        )
        assert refused.returncode != 0
        assert "refusing to overwrite precursor evidence" in refused.stderr

        collision.unlink()
        source.write_text("mutated evidence\n", encoding="utf-8")
        provenance_refused = run(
            prefix, summary, sensor, candidate, handoff, pre_retry_flash,
            evidence,
        )
        assert provenance_refused.returncode != 0
        assert "gate input provenance failed" in provenance_refused.stderr

        source.write_text("frozen evidence\n", encoding="utf-8")
        summary.write_text(
            json.dumps(
                {
                    "final_gate": {"passed": False},
                    "provenance": {"source": record(source)},
                }
            ),
            encoding="utf-8",
        )
        failed_gate = run(
            prefix, summary, sensor, candidate, handoff, pre_retry_flash,
            evidence,
        )
        assert failed_gate.returncode != 0
        assert "no engineering acceptance was supplied" in failed_gate.stderr

        acceptance = root / "engineering_acceptance.json"
        acceptance.write_text(
            json.dumps(
                {
                    "schema": "stratolink.engineering_acceptance.v1",
                    "accepted": True,
                    "decision": {
                        "source": "user",
                        "scope": "retry3_v15_hil",
                    },
                    "candidate": {
                        "elf_sha256": EXPECTED_ELF_SHA256,
                        "bin_sha256": EXPECTED_BIN_SHA256,
                    },
                    "accepted_deviations": [
                        {"id": "retry3_vstor_4558mv"},
                        {"id": "retry3_standby_host_permission"},
                    ],
                    "provenance": {"source": record(source)},
                }
            ),
            encoding="utf-8",
        )
        accepted = run(
            prefix,
            summary,
            sensor,
            candidate,
            handoff,
            pre_retry_flash,
            evidence,
            engineering_acceptance=acceptance,
        )
        assert accepted.returncode == 0, accepted.stdout + accepted.stderr

        summary.write_text(
            json.dumps(
                {
                    "final_gate": {"passed": True},
                    "provenance": {"source": record(source)},
                }
            ),
            encoding="utf-8",
        )
        wrong_jlink = run(
            prefix,
            summary,
            sensor,
            candidate,
            handoff,
            pre_retry_flash,
            evidence,
            jlink_serial="123456789",
        )
        assert wrong_jlink.returncode != 0
        assert "unrecognized J-Link serial" in wrong_jlink.stderr

        stale_rows = [
            {
                "utc": (now - timedelta(minutes=6)).isoformat(),
                "event": "ppk2_power_on",
                "source_mv": 4660,
                "reconnects": 0,
            },
            {
                "utc": (now - timedelta(minutes=5)).isoformat(),
                "event": "ppk2_power_heartbeat",
                "source_mv": 4660,
                "reconnects": 0,
            },
        ]
        handoff.write_text(
            "".join(json.dumps(row) + "\n" for row in stale_rows),
            encoding="utf-8",
        )
        stale = run(
            prefix, summary, sensor, candidate, handoff, pre_retry_flash,
            evidence,
        )
        assert stale.returncode != 0
        assert "heartbeat is stale" in stale.stderr

        fake_jlink = root / "fake-jlink"
        fake_jlink.write_text(
            "#!/bin/sh\nprintf 'Verification failed\\n'\nexit 0\n",
            encoding="utf-8",
        )
        fake_jlink.chmod(0o755)
        raw_output = root / "failed-jlink.txt"
        try:
            run_jlink(
                str(fake_jlink),
                "802007563",
                root / "unused.jlink",
                raw_output,
            )
        except SystemExit as error:
            assert "markers=['verification failed']" in str(error)
        else:
            raise AssertionError("J-Link failure text unexpectedly passed")
        assert raw_output.read_text(encoding="utf-8") == "Verification failed\n"

        successful_jlink = root / "successful-jlink"
        successful_jlink.write_text(
            "#!/bin/sh\n"
            "printf 'J-Link connection not established yet but required for command.\\n'\n"
            "printf 'Cortex-M4 identified.\\n'\n"
            "printf 'Script processing completed.\\n'\n",
            encoding="utf-8",
        )
        successful_jlink.chmod(0o755)
        successful_raw = root / "successful-jlink.txt"
        run_jlink(
            str(successful_jlink),
            "802007563",
            root / "unused.jlink",
            successful_raw,
        )
        assert "Script processing completed" in successful_raw.read_text(
            encoding="utf-8"
        )

    print("PASS: precursor preservation gate and create-once refusal")


if __name__ == "__main__":
    main()
