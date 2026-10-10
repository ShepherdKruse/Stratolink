#!/usr/bin/env python3
"""Exercise the Board1 development-flash wrapper without target access."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap

from flash_board1_development import (
    FLASH_ADDRESS,
    FLASH_BYTES,
    RESERVED_ADDRESS,
    RESERVED_BYTES,
    RESERVED_END_ADDRESS,
    RESERVED_OFFSET,
    artifact_paths,
    build_flash_script,
)


HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "flash_board1_development.py"
SERIAL = "802007563"


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def run_wrapper(
    prefix: Path,
    binary: Path,
    baseline: Path,
    expected_sha256: str,
    *,
    check_only: bool = False,
    initialize_reserved_erased: bool = False,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(SCRIPT),
        "--prefix",
        str(prefix),
        "--bin",
        str(binary),
        "--expected-bin-sha256",
        expected_sha256,
        "--baseline-flash",
        str(baseline),
        "--jlink-serial",
        SERIAL,
    ]
    if check_only:
        command.append("--check-only")
    if initialize_reserved_erased:
        command.append("--initialize-reserved-erased")
    return subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )


def install_fake_jlink(directory: Path) -> Path:
    executable = directory / "JLinkExe"
    executable.write_text(
        textwrap.dedent(
            f"""\
            #!{sys.executable}
            import os
            from pathlib import Path
            import shlex
            import sys

            arguments = sys.argv[1:]
            required = {{
                "-device": "STM32WLE5CC",
                "-if": "SWD",
                "-SelectEmuBySN": os.environ["EXPECTED_JLINK_SERIAL"],
                "-NoGui": "1",
                "-ExitOnError": "1",
            }}
            for flag, expected in required.items():
                try:
                    observed = arguments[arguments.index(flag) + 1]
                except (ValueError, IndexError):
                    print(f"missing {{flag}}", flush=True)
                    raise SystemExit(2)
                if observed != expected:
                    print(f"wrong {{flag}}: {{observed}}", flush=True)
                    raise SystemExit(2)

            script = Path(
                arguments[arguments.index("-CommanderScript") + 1]
            ).read_text(encoding="utf-8")
            lines = [line.strip() for line in script.splitlines() if line.strip()]
            before = None
            reserved_state = None
            mode = os.environ.get("FAKE_JLINK_MODE", "success")
            print(
                "J-Link connection not established yet but required for command.",
                flush=True,
            )
            print(f"S/N: {{required['-SelectEmuBySN']}}", flush=True)
            print('Device "STM32WLE5CC" selected.', flush=True)
            print("Cortex-M4 identified.", flush=True)
            for line in lines:
                words = shlex.split(line)
                command = words[0].lower()
                if command == "verifybin":
                    if before is None:
                        before = Path(words[1])
                        reserved_state = before.read_bytes()
                    print(f"J-Link>{{line}}", flush=True)
                    print("Verify successful.", flush=True)
                elif command == "loadfile":
                    print(f"J-Link>{{line}}", flush=True)
                    print(
                        "J-Link: Flash download: Total time 0.100s "
                        "(Prepare 0.010s, Compare 0.010s, Erase 0.020s, "
                        "Program 0.040s, Verify 0.020s)",
                        flush=True,
                    )
                    print("O.K.", flush=True)
                    if mode == "mass_erase":
                        print("Mass erase requested.", flush=True)
                    if mode == "unsecure":
                        print("Device will be unsecured now.", flush=True)
                elif command == "erase":
                    print(f"J-Link>{{line}}", flush=True)
                    if mode == "broad_erase":
                        print("J-Link>erase", flush=True)
                    reserved_state = b"\\xFF" * {RESERVED_BYTES}
                    print("Erase done.", flush=True)
                elif command == "savebin":
                    if before is None or reserved_state is None:
                        print("missing pre-flash reserved page", flush=True)
                        raise SystemExit(2)
                    output = Path(words[1])
                    value = reserved_state
                    if mode == "reserved_mismatch":
                        value = bytes([value[0] ^ 0xFF]) + value[1:]
                    output.write_bytes(value)
                    print(f"J-Link>{{line}}", flush=True)
                    print("O.K.", flush=True)
                elif command in {{"r", "g"}}:
                    print(f"J-Link>{{line}}", flush=True)
            print("Script processing completed.", flush=True)
            """
        ),
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


def main() -> None:
    with tempfile.TemporaryDirectory(
        prefix="stratolink-board1-development-flash-test-"
    ) as raw:
        root = Path(raw)
        binary_bytes = bytes(range(251)) * 7
        binary = root / "development.bin"
        binary.write_bytes(binary_bytes)
        expected_sha256 = sha256(binary_bytes)

        baseline_bytes = bytes(range(256)) * (FLASH_BYTES // 256)
        baseline = root / "board1_baseline_flash.bin"
        baseline.write_bytes(baseline_bytes)
        baseline_sha256 = sha256(baseline_bytes)
        reserved_bytes = baseline_bytes[
            RESERVED_OFFSET : RESERVED_OFFSET + RESERVED_BYTES
        ]

        paths = artifact_paths(root / "script_shape")
        script = build_flash_script(paths)
        commands = [line.strip() for line in script.splitlines() if line.strip()]
        load_commands = [line for line in commands if line.startswith("loadfile ")]
        verify_commands = [line for line in commands if line.startswith("verifybin ")]
        assert len(load_commands) == 1
        assert f"0x{FLASH_ADDRESS:08X}" in load_commands[0]
        assert load_commands[0].endswith(" noreset")
        assert len(verify_commands) == 3
        assert f"0x{RESERVED_ADDRESS:08X}" in verify_commands[0]
        assert f"0x{RESERVED_ADDRESS:08X}" in verify_commands[-1]
        assert any(line.startswith("savebin ") for line in commands)
        assert commands[-3:] == ["r", "g", "exit"]
        assert not any(
            line.lower().startswith(("erase", "unlock", "unsecure"))
            for line in commands
        )

        initialize_paths = artifact_paths(root / "initialize_shape")
        initialize_script = build_flash_script(
            initialize_paths,
            initialize_reserved_erased=True,
        )
        initialize_commands = [
            line.strip()
            for line in initialize_script.splitlines()
            if line.strip()
        ]
        assert [
            line for line in initialize_commands if line.startswith("erase ")
        ] == [
            f"erase 0x{RESERVED_ADDRESS:08X} "
            f"0x{RESERVED_END_ADDRESS:08X} noreset"
        ]
        assert len(
            [line for line in initialize_commands if line.startswith("loadfile ")]
        ) == 1
        assert len(
            [line for line in initialize_commands if line.startswith("verifybin ")]
        ) == 4

        ready = run_wrapper(
            root / "check_only",
            binary,
            baseline,
            expected_sha256,
            check_only=True,
        )
        assert ready.returncode == 0, ready.stdout + ready.stderr
        ready_value = json.loads(ready.stdout)
        assert ready_value["ready"] is True
        assert ready_value["candidate"]["sha256"] == expected_sha256
        assert ready_value["target"]["jlink_serial"] == SERIAL
        assert not any(
            path.exists() for path in artifact_paths(root / "check_only").values()
        )

        wrong_hash = run_wrapper(
            root / "wrong_hash",
            binary,
            baseline,
            "0" * 64,
            check_only=True,
        )
        assert wrong_hash.returncode != 0
        assert "BIN SHA-256 mismatch" in wrong_hash.stderr

        overlapping = root / "overlapping.bin"
        overlapping.write_bytes(b"X" * (RESERVED_OFFSET + 1))
        overlap = run_wrapper(
            root / "overlap",
            overlapping,
            baseline,
            sha256(overlapping.read_bytes()),
            check_only=True,
        )
        assert overlap.returncode != 0
        assert "overlaps the opaque reserved page" in overlap.stderr

        fake_bin = root / "fake-bin"
        fake_bin.mkdir()
        install_fake_jlink(fake_bin)
        environment = os.environ.copy()
        environment["PATH"] = str(fake_bin) + os.pathsep + environment.get("PATH", "")
        environment["EXPECTED_JLINK_SERIAL"] = SERIAL

        success_prefix = root / "success"
        success = run_wrapper(
            success_prefix,
            binary,
            baseline,
            expected_sha256,
            environment=environment,
        )
        assert success.returncode == 0, success.stdout + success.stderr
        success_paths = artifact_paths(success_prefix)
        manifest = json.loads(success_paths["manifest"].read_text(encoding="utf-8"))
        assert manifest["passed"] is True
        assert manifest["target"]["jlink_serial"] == SERIAL
        assert manifest["candidate"]["required_sha256"] == expected_sha256
        assert manifest["candidate"]["program_address"] == "0x08000000"
        assert manifest["reserved_page"]["byte_identical"] is True
        assert manifest["programming"]["transcript"]["loadfile_command_count"] == 1
        assert manifest["programming"]["transcript"]["verifybin_command_count"] == 3
        assert manifest["programming"]["transcript"][
            "benign_commander_connect_preamble_seen"
        ] is True
        assert success_paths["reserved_before"].read_bytes() == reserved_bytes
        assert success_paths["reserved_after"].read_bytes() == reserved_bytes
        assert sha256(baseline.read_bytes()) == baseline_sha256

        initialize_prefix = root / "initialize"
        initialize = run_wrapper(
            initialize_prefix,
            binary,
            baseline,
            expected_sha256,
            initialize_reserved_erased=True,
            environment=environment,
        )
        assert initialize.returncode == 0, initialize.stdout + initialize.stderr
        initialize_artifacts = artifact_paths(initialize_prefix)
        initialize_manifest = json.loads(
            initialize_artifacts["manifest"].read_text(encoding="utf-8")
        )
        assert initialize_manifest["passed"] is True
        assert initialize_manifest["reserved_page"]["action"] == "initialize_erased"
        assert initialize_manifest["reserved_page"]["before_preserved_as_evidence"] is True
        assert initialize_manifest["reserved_page"]["byte_identical"] is False
        assert initialize_manifest["reserved_page"][
            "matches_requested_post_flash_state"
        ] is True
        assert initialize_artifacts["reserved_before"].read_bytes() == reserved_bytes
        assert initialize_artifacts["reserved_erased"].read_bytes() == b"\xFF" * RESERVED_BYTES
        assert initialize_artifacts["reserved_after"].read_bytes() == b"\xFF" * RESERVED_BYTES
        initialize_transcript = initialize_manifest["programming"]["transcript"]
        assert initialize_transcript["erase_command_count"] == 1
        assert initialize_transcript["bounded_reserved_erase_seen"] is True
        assert initialize_transcript["verifybin_command_count"] == 4

        broad_environment = environment.copy()
        broad_environment["FAKE_JLINK_MODE"] = "broad_erase"
        broad_prefix = root / "broad_erase"
        broad = run_wrapper(
            broad_prefix,
            binary,
            baseline,
            expected_sha256,
            initialize_reserved_erased=True,
            environment=broad_environment,
        )
        assert broad.returncode != 0
        broad_manifest = json.loads(
            artifact_paths(broad_prefix)["manifest"].read_text(encoding="utf-8")
        )
        assert broad_manifest["passed"] is False
        assert broad_manifest["programming"]["transcript"][
            "bounded_reserved_erase_seen"
        ] is False

        collision = run_wrapper(
            success_prefix,
            binary,
            baseline,
            expected_sha256,
            environment=environment,
        )
        assert collision.returncode != 0
        assert "refusing to overwrite Board1 development-flash evidence" in collision.stderr

        forbidden_environment = environment.copy()
        forbidden_environment["FAKE_JLINK_MODE"] = "mass_erase"
        forbidden_prefix = root / "forbidden"
        forbidden = run_wrapper(
            forbidden_prefix,
            binary,
            baseline,
            expected_sha256,
            environment=forbidden_environment,
        )
        assert forbidden.returncode != 0
        forbidden_manifest = json.loads(
            artifact_paths(forbidden_prefix)["manifest"].read_text(encoding="utf-8")
        )
        assert forbidden_manifest["passed"] is False
        assert "mass erase" in forbidden_manifest["programming"]["transcript"][
            "forbidden_mutation_markers"
        ]

        unsecure_environment = environment.copy()
        unsecure_environment["FAKE_JLINK_MODE"] = "unsecure"
        unsecure_prefix = root / "unsecure"
        unsecure = run_wrapper(
            unsecure_prefix,
            binary,
            baseline,
            expected_sha256,
            environment=unsecure_environment,
        )
        assert unsecure.returncode != 0
        unsecure_manifest = json.loads(
            artifact_paths(unsecure_prefix)["manifest"].read_text(encoding="utf-8")
        )
        assert "device will be unsecured" in unsecure_manifest["programming"][
            "transcript"
        ]["forbidden_mutation_markers"]

        mismatch_environment = environment.copy()
        mismatch_environment["FAKE_JLINK_MODE"] = "reserved_mismatch"
        mismatch_prefix = root / "reserved_mismatch"
        mismatch = run_wrapper(
            mismatch_prefix,
            binary,
            baseline,
            expected_sha256,
            environment=mismatch_environment,
        )
        assert mismatch.returncode != 0
        mismatch_manifest = json.loads(
            artifact_paths(mismatch_prefix)["manifest"].read_text(encoding="utf-8")
        )
        assert mismatch_manifest["passed"] is False
        assert mismatch_manifest["reserved_page"]["byte_identical"] is False
        assert (
            "opaque reserved page does not match the requested post-flash state"
            in mismatch_manifest["failures"]
        )

    print("Board1 development-flash wrapper tests passed (fake J-Link only).")


if __name__ == "__main__":
    main()
