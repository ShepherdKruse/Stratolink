#!/usr/bin/env python3
"""Exercise flight-flash preconditions without accessing the target."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from evidence_provenance import record
from preserve_precursor import (
    DEFAULT_PRE_RETRY_FLASH,
    EXPECTED_PRE_RETRY_FLASH_SHA256,
    FLASH_OPTR_IWDG_STOP,
    sha256,
)
from verify_flight_candidate import EXPECTED_BIN_SHA256, EXPECTED_ELF_SHA256


HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "flash_flight_candidate.py"


def artifact_record(path: Path) -> dict:
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def run(
    prefix: Path,
    summary: Path,
    sensor: Path,
    candidate: Path,
    precursor: Path,
    handoff: Path,
    engineering_acceptance: Path | None = None,
    devnonce_baseline: Path | None = None,
    devnonce_manifest: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [
            sys.executable,
            str(SCRIPT),
            "--check-only",
            "--prefix",
            str(prefix),
            "--summary",
            str(summary),
            "--sensor-model",
            str(sensor),
            "--candidate-verification",
            str(candidate),
            "--precursor-manifest",
            str(precursor),
            "--handoff-power",
            str(handoff),
        ]
    if engineering_acceptance is not None:
        command.extend(
            ["--engineering-acceptance", str(engineering_acceptance)]
        )
    if devnonce_baseline is not None:
        command.extend(["--devnonce-baseline", str(devnonce_baseline)])
    if devnonce_manifest is not None:
        command.extend(["--devnonce-manifest", str(devnonce_manifest)])
    return subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
    )


def main() -> None:
    bare = subprocess.run(
        [sys.executable, str(SCRIPT), "--check-only"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert bare.returncode != 0
    assert "the following arguments are required" in bare.stderr

    with tempfile.TemporaryDirectory(prefix="stratolink-flash-gate-test-") as raw:
        root = Path(raw)
        source = root / "source.log"
        source.write_text("immutable\n", encoding="utf-8")
        provenance = {"source": record(source)}
        precursor_source = root / "precursor_source.log"
        precursor_source.write_text("precursor immutable\n", encoding="utf-8")
        precursor_provenance = {"source": record(precursor_source)}
        superseded_elf = str(
            (HERE.parents[1] / "firmware/.pio/build/stratolink/firmware.elf").resolve()
        )
        superseded_bin = str(
            (HERE.parents[1] / "firmware/.pio/build/stratolink/firmware.bin").resolve()
        )
        precursor_provenance.update(
            {
                superseded_elf: {
                    "path": superseded_elf,
                    "bytes": 239736,
                    "sha256": "32d98b6416f74315cb14455f0fb71c1e795bf6699be531d2b8749177e82d8439",
                    "append_allowed": False,
                },
                superseded_bin: {
                    "path": superseded_bin,
                    "bytes": 132820,
                    "sha256": "92876b738d48b437b1238061ab1a8c3e66f12ac595c406905447208c1d1fdf2d",
                    "append_allowed": False,
                },
            }
        )

        summary = root / "summary.json"
        summary.write_text(
            json.dumps(
                {
                    "final_gate": {"passed": True},
                    "provenance": provenance,
                }
            ),
            encoding="utf-8",
        )
        sensor = root / "sensor.json"
        sensor.write_text(
            json.dumps({"passed": True, "provenance": provenance}),
            encoding="utf-8",
        )
        candidate = root / "candidate.json"
        candidate.write_text(
            json.dumps(
                {
                    "passed": True,
                    "candidate": {
                        "elf_sha256": EXPECTED_ELF_SHA256,
                        "bin_sha256": EXPECTED_BIN_SHA256,
                    },
                    "provenance": provenance,
                }
            ),
            encoding="utf-8",
        )

        flash = DEFAULT_PRE_RETRY_FLASH
        ram = root / "precursor_ram.bin"
        optr = root / "precursor_flash_optr.bin"
        assert flash.is_file(), "fixed pre-retry flash baseline is absent"
        assert sha256(flash) == EXPECTED_PRE_RETRY_FLASH_SHA256
        ram.write_bytes(b"\x00" * (64 * 1024))
        optr.write_bytes(FLASH_OPTR_IWDG_STOP.to_bytes(4, "little"))
        precursor = root / "precursor_manifest.json"
        precursor_value = {
            "target": {"jlink_serial": "802007563"},
            "flash_unchanged_during_soak": True,
            "precursor": {
                "flash": artifact_record(flash),
                "ram": artifact_record(ram),
                "flash_optr": artifact_record(optr),
            },
            "pre_retry_flash": artifact_record(flash),
            "flash_option_register": {
                **artifact_record(optr),
                "iwdg_runs_in_stop": True,
            },
            "evidence_inputs": precursor_provenance,
        }
        precursor.write_text(json.dumps(precursor_value), encoding="utf-8")

        handoff = root / "handoff.jsonl"
        now = datetime.now(timezone.utc)
        handoff_rows = [
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
        ]
        handoff.write_text(
            "".join(json.dumps(row) + "\n" for row in handoff_rows),
            encoding="utf-8",
        )
        prefix = root / "flight_flash"

        ready = run(prefix, summary, sensor, candidate, precursor, handoff)
        assert ready.returncode == 0, ready.stdout + ready.stderr
        assert '"ready": true' in ready.stdout

        journal = root / "devnonce.bin"
        journal.write_bytes(b"\xFF" * 4096)
        journal_manifest = root / "devnonce_manifest.json"
        journal_manifest.write_text(
            json.dumps(
                {
                    "passed": True,
                    "target": {"jlink_serial": "802007563"},
                    "candidate_verification_sha256": sha256(candidate),
                    "journal": {
                        "invalid_record_count": 0,
                        "exhausted": False,
                        "valid_record_count": 1,
                    },
                    "artifacts": {"journal": artifact_record(journal)},
                }
            ),
            encoding="utf-8",
        )
        post_hil_ready = run(
            root / "post_hil_flash",
            summary,
            sensor,
            candidate,
            precursor,
            handoff,
            devnonce_baseline=journal,
            devnonce_manifest=journal_manifest,
        )
        assert post_hil_ready.returncode == 0, (
            post_hil_ready.stdout + post_hil_ready.stderr
        )
        assert '"reserved_baseline_source": "passing_post_hil_devnonce_capture"' in post_hil_ready.stdout

        missing_pair = run(
            root / "missing_pair",
            summary,
            sensor,
            candidate,
            precursor,
            handoff,
            devnonce_baseline=journal,
        )
        assert missing_pair.returncode != 0
        assert "supply both" in missing_pair.stderr

        precursor_value["flash_unchanged_during_soak"] = False
        precursor.write_text(json.dumps(precursor_value), encoding="utf-8")
        changed = run(prefix, summary, sensor, candidate, precursor, handoff)
        assert changed.returncode != 0
        assert "does not prove unchanged soak flash" in changed.stderr
        precursor_value["flash_unchanged_during_soak"] = True

        precursor_value["pre_retry_flash"]["sha256"] = "0" * 64
        precursor.write_text(json.dumps(precursor_value), encoding="utf-8")
        wrong_baseline = run(prefix, summary, sensor, candidate, precursor, handoff)
        assert wrong_baseline.returncode != 0
        assert "no longer matches its manifest" in wrong_baseline.stderr
        precursor_value["pre_retry_flash"] = artifact_record(flash)

        precursor.write_text(json.dumps(precursor_value), encoding="utf-8")
        precursor_source.write_text("mutated\n", encoding="utf-8")
        stale_provenance = run(prefix, summary, sensor, candidate, precursor, handoff)
        assert stale_provenance.returncode != 0
        assert "precursor evidence provenance failed" in stale_provenance.stderr
        precursor_source.write_text("precursor immutable\n", encoding="utf-8")
        precursor.write_text(json.dumps(precursor_value), encoding="utf-8")

        collision = prefix.with_name(prefix.name + "_raw.txt")
        collision.write_text("existing evidence", encoding="utf-8")
        refused = run(prefix, summary, sensor, candidate, precursor, handoff)
        assert refused.returncode != 0
        assert "refusing to overwrite flash evidence" in refused.stderr
        collision.unlink()

        handoff_rows[-1]["utc"] = (now - timedelta(minutes=5)).isoformat()
        handoff.write_text(
            "".join(json.dumps(row) + "\n" for row in handoff_rows),
            encoding="utf-8",
        )
        stale = run(prefix, summary, sensor, candidate, precursor, handoff)
        assert stale.returncode != 0
        assert "heartbeat is stale" in stale.stderr

    print("PASS: flash gate readiness, create-once refusal, and live-power check")


if __name__ == "__main__":
    main()
