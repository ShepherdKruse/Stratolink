#!/usr/bin/env python3
"""Adversarial host regression for Board1 launch-authority provisioning."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from provision_board1_launch_authority import (
    BKP18_OFFSET,
    REGIONS,
    TAMP_LEASE_MAGIC,
    TAMP_REGION_AUTHORITY_GNSS,
    TAMP_REGION_LEASE_MAGIC,
    artifact_paths,
    build_preflight_script,
    build_write_script,
    classify_write_transcript,
    decode_valid_authority,
    encode_launch_authority,
    tamp_region_lease_crc8,
)


HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "provision_board1_launch_authority.py"

EXPECTED_RECORDS = {
    "us915": 0x5B6E6000,
    "eu868": 0x5B606800,
    "as923": 0x5B727000,
    "au915": 0x5B7C7800,
}

FAKE_JLINK = r'''#!/usr/bin/env python3
import os
from pathlib import Path
import re
import sys

args = sys.argv[1:]
script_path = Path(args[args.index("-CommanderScript") + 1])
serial = args[args.index("-SelectEmuBySN") + 1]
script = script_path.read_text(encoding="utf-8")
commands = [line.strip() for line in script.splitlines() if line.strip()]
mode = os.environ.get("FAKE_JLINK_MODE", "happy")
state_path = Path(os.environ["FAKE_JLINK_STATE"])
calls_path = Path(os.environ["FAKE_JLINK_CALLS"])
write_count_path = Path(os.environ["FAKE_JLINK_WRITES"])
state = bytearray(state_path.read_bytes())
phase = "write" if any(line.lower().startswith("w4 ") for line in commands) else "preflight"
with calls_path.open("a", encoding="utf-8") as handle:
    handle.write(phase + "\n")

print("SEGGER J-Link Commander")
print(f"S/N: {serial}")
print('Device "STM32WLE5CC" selected.')
print("Cortex-M4 identified.")
if phase == "preflight":
    print("Can not attach to CPU. Trying connect under reset.")

for command in commands:
    print(f"J-Link>{command}")
    lower = command.lower()
    if lower.startswith("sleep "):
        print(f"Sleep({command.split()[1]})")
    elif lower.startswith("verifybin "):
        source = Path(re.match(r'^verifybin "([^"]+)"', command, re.I).group(1))
        if source.read_bytes() != state or mode == "toctou":
            print("Verification failed")
            print("Script processing completed.")
            sys.exit(1)
        print("Verify successful.")
    elif lower.startswith("w4 "):
        record = int(command.split()[2], 0)
        if mode == "wrong-write":
            record ^= 1
        state[72:76] = record.to_bytes(4, "little")
        if mode == "other-tamp-write":
            state[0] ^= 1
        state_path.write_bytes(state)
        count = int(write_count_path.read_text(encoding="utf-8")) + 1
        write_count_path.write_text(str(count), encoding="utf-8")
    elif lower.startswith("mem32 "):
        record = int.from_bytes(state[72:76], "little")
        print(f"4000B148 = {record:08X}")
        if phase == "write" and mode == "extra-write":
            print("J-Link>w4 0x4000B100 0xDEADBEEF")
    elif lower.startswith("savebin "):
        destination = Path(re.match(r'^savebin "([^"]+)"', command, re.I).group(1))
        destination.write_bytes(state)

if phase == "write" and mode == "forbidden":
    print("J-Link>erase")
    print("Mass erase initiated")
print("Script processing completed.")
'''


def legacy_record(age_sec: int) -> int:
    age = min(age_sec, 0x7FF)
    return (TAMP_LEASE_MAGIC << 22) | (((~age) & 0x7FF) << 11) | age


def v2_record(age_sec: int, region_id: int, source_id: int) -> int:
    payload = min(age_sec, 0x7FF) | (region_id << 11) | (source_id << 13)
    return (
        (TAMP_REGION_LEASE_MAGIC << 22)
        | (tamp_region_lease_crc8(payload) << 14)
        | payload
    )


def set_state_word(state_path: Path, word: int) -> None:
    state = bytearray(range(80))
    state[BKP18_OFFSET : BKP18_OFFSET + 4] = word.to_bytes(4, "little")
    state_path.write_bytes(state)


def run_tool(
    prefix: Path,
    fake_bin: Path,
    state_path: Path,
    calls_path: Path,
    writes_path: Path,
    *,
    region: str = "us915",
    mode: str = "happy",
    check_only: bool = False,
    development_rearm: bool = False,
    serial: str = "802007563",
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(SCRIPT),
        "--prefix",
        str(prefix),
        "--region",
        region,
        "--jlink-serial",
        serial,
        "--speed-khz",
        "100",
    ]
    if check_only:
        command.append("--check-only")
    if development_rearm:
        command.append("--development-rearm-expired-us915")
    environment = dict(os.environ)
    environment["PATH"] = str(fake_bin) + os.pathsep + environment["PATH"]
    environment["FAKE_JLINK_MODE"] = mode
    environment["FAKE_JLINK_STATE"] = str(state_path)
    environment["FAKE_JLINK_CALLS"] = str(calls_path)
    environment["FAKE_JLINK_WRITES"] = str(writes_path)
    return subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )


def main() -> None:
    assert set(REGIONS) == set(EXPECTED_RECORDS)
    for region, region_id in REGIONS.items():
        record = encode_launch_authority(region_id)
        assert record == EXPECTED_RECORDS[region]
        decoded = decode_valid_authority(record)
        assert decoded is not None
        assert decoded["format"] == "v2"
        assert decoded["source"] == "LAUNCH"
        assert decoded["age_sec"] == 0

    assert decode_valid_authority(0) is None
    assert decode_valid_authority(legacy_record(123))["format"] == "legacy"
    gnss = decode_valid_authority(v2_record(456, 2, TAMP_REGION_AUTHORITY_GNSS))
    assert gnss is not None and gnss["source"] == "GNSS"
    assert gnss["region"] == "as923"
    assert decode_valid_authority(EXPECTED_RECORDS["us915"] ^ 1) is None

    with tempfile.TemporaryDirectory(prefix="stratolink-launch-authority-") as raw:
        root = Path(raw)
        fake_bin = root / "bin"
        fake_bin.mkdir()
        fake_jlink = fake_bin / "JLinkExe"
        fake_jlink.write_text(FAKE_JLINK, encoding="utf-8")
        fake_jlink.chmod(0o755)
        state_path = root / "device_tamp.bin"
        calls_path = root / "calls.txt"
        writes_path = root / "writes.txt"
        calls_path.write_text("", encoding="utf-8")
        writes_path.write_text("0", encoding="utf-8")
        set_state_word(state_path, 0)

        happy_prefix = root / "happy"
        ready = run_tool(
            happy_prefix,
            fake_bin,
            state_path,
            calls_path,
            writes_path,
            check_only=True,
        )
        assert ready.returncode == 0, ready.stdout + ready.stderr
        assert '"record": "0x5B6E6000"' in ready.stdout
        assert json.loads(ready.stdout)["development_rearm_expired_us915"] is False
        assert not any(path.exists() for path in artifact_paths(happy_prefix).values())

        happy = run_tool(
            happy_prefix, fake_bin, state_path, calls_path, writes_path
        )
        assert happy.returncode == 0, happy.stdout + happy.stderr
        happy_paths = artifact_paths(happy_prefix)
        manifest = json.loads(happy_paths["manifest"].read_text(encoding="utf-8"))
        assert manifest["passed"] is True
        assert manifest["development_rearm_expired_us915"] is False
        assert manifest["state_gate"]["passed"] is True
        assert manifest["state_gate"]["write_attempted"] is True
        assert manifest["verification"]["exact_word_verified"] is True
        assert manifest["verification"]["all_other_tamp_bytes_unchanged"] is True
        assert manifest["verification"]["reset_and_run_issued"] is True
        assert manifest["transport"]["preflight"]["connected_under_reset"] is True
        assert manifest["transport"]["preflight"]["startup_recovery_proved"] is True
        assert manifest["transport"]["preflight"]["write_command_count"] == 0
        assert manifest["transport"]["write"]["write_command_count"] == 1
        assert calls_path.read_text(encoding="utf-8").splitlines() == [
            "preflight",
            "write",
        ]
        assert writes_path.read_text(encoding="utf-8") == "1"

        # A different evidence prefix cannot overwrite the live valid record.
        # Only the read-only preflight subprocess is launched.
        second_prefix = root / "second-prefix"
        second = run_tool(
            second_prefix, fake_bin, state_path, calls_path, writes_path
        )
        assert second.returncode != 0
        second_manifest = json.loads(
            artifact_paths(second_prefix)["manifest"].read_text(encoding="utf-8")
        )
        assert second_manifest["state_gate"]["passed"] is False
        assert second_manifest["state_gate"]["write_attempted"] is False
        assert second_manifest["state_gate"]["existing_valid_authority"][
            "source"
        ] == "LAUNCH"
        assert second_manifest["transport"]["write"] is None
        assert calls_path.read_text(encoding="utf-8").splitlines() == [
            "preflight",
            "write",
            "preflight",
        ]
        assert writes_path.read_text(encoding="utf-8") == "1"
        assert not artifact_paths(second_prefix)["write_script"].exists()
        assert not artifact_paths(second_prefix)["write_raw"].exists()

        collision = run_tool(
            happy_prefix,
            fake_bin,
            state_path,
            calls_path,
            writes_path,
            check_only=True,
        )
        assert collision.returncode != 0
        assert "refusing to overwrite Board1 launch-authority evidence" in collision.stderr

        # Both valid historical record classes reject before any write process.
        for label, existing in (
            ("legacy", legacy_record(1800)),
            ("gnss", v2_record(1800, 1, TAMP_REGION_AUTHORITY_GNSS)),
        ):
            set_state_word(state_path, existing)
            calls_before = calls_path.read_text(encoding="utf-8").splitlines()
            writes_before = writes_path.read_text(encoding="utf-8")
            prefix = root / label
            rejected = run_tool(
                prefix, fake_bin, state_path, calls_path, writes_path
            )
            assert rejected.returncode != 0
            rejected_manifest = json.loads(
                artifact_paths(prefix)["manifest"].read_text(encoding="utf-8")
            )
            assert rejected_manifest["state_gate"]["passed"] is False
            assert rejected_manifest["state_gate"]["write_attempted"] is False
            expected_format = "legacy" if label == "legacy" else "v2"
            assert rejected_manifest["state_gate"]["existing_valid_authority"][
                "format"
            ] == expected_format
            assert calls_path.read_text(encoding="utf-8").splitlines() == (
                calls_before + ["preflight"]
            )
            assert writes_path.read_text(encoding="utf-8") == writes_before

        # A changed target between phases fails verifybin before the w4.
        set_state_word(state_path, 0)
        writes_before = writes_path.read_text(encoding="utf-8")
        toctou_prefix = root / "toctou"
        toctou = run_tool(
            toctou_prefix,
            fake_bin,
            state_path,
            calls_path,
            writes_path,
            mode="toctou",
        )
        assert toctou.returncode != 0
        toctou_manifest = json.loads(
            artifact_paths(toctou_prefix)["manifest"].read_text(encoding="utf-8")
        )
        assert toctou_manifest["transport"]["write"]["passed"] is False
        assert writes_path.read_text(encoding="utf-8") == writes_before

        development_check_prefix = root / "development-check-only"
        calls_before = calls_path.read_text(encoding="utf-8")
        development_ready = run_tool(
            development_check_prefix, fake_bin, state_path, calls_path, writes_path,
            development_rearm=True, check_only=True,
        )
        assert development_ready.returncode == 0
        assert json.loads(development_ready.stdout)["development_rearm_expired_us915"] is True
        assert calls_path.read_text(encoding="utf-8") == calls_before
        assert not any(
            path.exists() for path in artifact_paths(development_check_prefix).values()
        )

        set_state_word(state_path, 0)
        wrong_prefix = root / "wrong"
        wrong = run_tool(
            wrong_prefix,
            fake_bin,
            state_path,
            calls_path,
            writes_path,
            mode="wrong-write",
        )
        assert wrong.returncode != 0
        wrong_manifest = json.loads(
            artifact_paths(wrong_prefix)["manifest"].read_text(encoding="utf-8")
        )
        assert wrong_manifest["verification"]["exact_word_verified"] is False
        assert "exact BKP18 mem32 readback was not observed" in (
            wrong_manifest["transport"]["write"]["required_failures"]
        )

        set_state_word(state_path, 0)
        forbidden_prefix = root / "forbidden"
        forbidden = run_tool(
            forbidden_prefix,
            fake_bin,
            state_path,
            calls_path,
            writes_path,
            mode="forbidden",
        )
        assert forbidden.returncode != 0
        forbidden_manifest = json.loads(
            artifact_paths(forbidden_prefix)["manifest"].read_text(encoding="utf-8")
        )
        assert forbidden_manifest["transport"]["write"]["forbidden_commands"] == [
            "erase"
        ]
        assert "mass erase" in forbidden_manifest["transport"]["write"][
            "forbidden_mutation_markers"
        ]

        set_state_word(state_path, 0)
        extra_prefix = root / "extra"
        extra = run_tool(
            extra_prefix,
            fake_bin,
            state_path,
            calls_path,
            writes_path,
            mode="extra-write",
        )
        assert extra.returncode != 0
        extra_manifest = json.loads(
            artifact_paths(extra_prefix)["manifest"].read_text(encoding="utf-8")
        )
        assert extra_manifest["transport"]["write"]["write_command_count"] == 2

        fixture_paths = artifact_paths(root / "script")
        preflight_script = build_preflight_script(fixture_paths)
        assert "connect\nh\ng\nsleep 5000\nh\n" in preflight_script
        assert "\nw4 " not in preflight_script
        write_script = build_write_script(fixture_paths, EXPECTED_RECORDS["eu868"])
        assert write_script.count("\nw4 ") == 1
        assert "verifybin" in write_script
        lowered = write_script.lower()
        for forbidden_name in ("erase", "loadfile", "loadbin", "unlock", "unsecure"):
            assert forbidden_name not in lowered

        direct = classify_write_transcript(
            "\n".join(
                [
                    "S/N: 802007563",
                    'Device "STM32WLE5CC" selected.',
                    "Cortex-M4 identified.",
                    "J-Link>program firmware.bin",
                    "Script processing completed.",
                ]
            ),
            0,
            expected_serial="802007563",
            expected_record=EXPECTED_RECORDS["us915"],
        )
        assert direct["passed"] is False
        assert direct["forbidden_commands"] == ["program firmware.bin"]

        # Rearming is a deliberate operation on this US bench, never a new
        # evidence prefix that silently relaxes the create-once default.
        expired = v2_record(1800, REGIONS["us915"], 1)
        set_state_word(state_path, expired)
        writes_before = writes_path.read_text(encoding="utf-8")
        default_expired = run_tool(
            root / "default-expired", fake_bin, state_path, calls_path, writes_path
        )
        assert default_expired.returncode != 0
        assert writes_path.read_text(encoding="utf-8") == writes_before

        for label, existing in (
            ("expired-boundary", expired),
            ("expired-saturated", v2_record(2047, REGIONS["us915"], 1)),
            ("blank", 0),
        ):
            set_state_word(state_path, existing)
            prefix = root / f"development-{label}"
            calls_before = calls_path.read_text(encoding="utf-8").splitlines()
            writes_before = int(writes_path.read_text(encoding="utf-8"))
            rearmed = run_tool(
                prefix, fake_bin, state_path, calls_path, writes_path,
                development_rearm=True,
            )
            assert rearmed.returncode == 0, rearmed.stdout + rearmed.stderr
            rearm_manifest = json.loads(
                artifact_paths(prefix)["manifest"].read_text(encoding="utf-8")
            )
            assert rearm_manifest["development_rearm_expired_us915"] is True
            assert rearm_manifest["state_gate"]["existing_valid_authority"] == (
                decode_valid_authority(existing)
            )
            assert rearm_manifest["state_gate"]["before_word"] == f"0x{existing:08X}"
            assert rearm_manifest["passed"] is True
            assert rearm_manifest["verification"]["all_other_tamp_bytes_unchanged"] is True
            assert rearm_manifest["transport"]["write"]["write_command_count"] == 1
            assert calls_path.read_text(encoding="utf-8").splitlines() == (
                calls_before + ["preflight", "write"]
            )
            assert int(writes_path.read_text(encoding="utf-8")) == writes_before + 1

        # Check every provenance/region at the age boundary and saturation.
        rejected_records = [legacy_record(age) for age in (0, 1799, 1800, 2047)]
        rejected_records += [
            v2_record(age, region_id, source_id)
            for region_id in REGIONS.values()
            for source_id in (0, 1)
            for age in (0, 1799, 1800, 2047)
            if not (region_id == REGIONS["us915"] and source_id == 1 and age >= 1800)
        ]
        for index, existing in enumerate(rejected_records):
            set_state_word(state_path, existing)
            prefix = root / f"development-rejected-{index}"
            writes_before = writes_path.read_text(encoding="utf-8")
            calls_before = calls_path.read_text(encoding="utf-8").splitlines()
            rejected = run_tool(
                prefix, fake_bin, state_path, calls_path, writes_path,
                development_rearm=True,
            )
            assert rejected.returncode != 0
            rejected_manifest = json.loads(
                artifact_paths(prefix)["manifest"].read_text(encoding="utf-8")
            )
            assert rejected_manifest["development_rearm_expired_us915"] is True
            assert rejected_manifest["state_gate"]["write_attempted"] is False
            assert rejected_manifest["state_gate"]["existing_valid_authority"] == (
                decode_valid_authority(existing)
            )
            assert not artifact_paths(prefix)["write_script"].exists()
            assert calls_path.read_text(encoding="utf-8").splitlines() == (
                calls_before + ["preflight"]
            )
            assert writes_path.read_text(encoding="utf-8") == writes_before

        for index, (region, serial) in enumerate([
            (region, "802007563") for region in REGIONS if region != "us915"
        ] + [("us915", "802007564")]):
            prefix = root / f"development-wrong-target-{index}"
            calls_before = calls_path.read_text(encoding="utf-8")
            invalid = run_tool(
                prefix, fake_bin, state_path, calls_path, writes_path,
                region=region, serial=serial, development_rearm=True,
            )
            assert invalid.returncode != 0
            assert "requires --region us915 and --jlink-serial 802007563" in invalid.stderr
            assert calls_path.read_text(encoding="utf-8") == calls_before
            assert not any(path.exists() for path in artifact_paths(prefix).values())

        for mode in ("toctou", "wrong-write", "extra-write", "other-tamp-write", "forbidden"):
            set_state_word(state_path, expired)
            prefix = root / f"development-{mode}"
            writes_before = writes_path.read_text(encoding="utf-8")
            guarded = run_tool(
                prefix, fake_bin, state_path, calls_path, writes_path,
                mode=mode, development_rearm=True,
            )
            assert guarded.returncode != 0
            guarded_manifest = json.loads(
                artifact_paths(prefix)["manifest"].read_text(encoding="utf-8")
            )
            assert guarded_manifest["passed"] is False
            if mode == "toctou":
                assert writes_path.read_text(encoding="utf-8") == writes_before
            if mode == "other-tamp-write":
                assert guarded_manifest["verification"]["all_other_tamp_bytes_unchanged"] is False

    print(
        "PASS: launch authority is device-state create-once, TOCTOU-closed, "
        "startup-safe; explicit US bench rearm only accepts expired US LAUNCH "
        "and preserves all mutation safeguards"
    )


if __name__ == "__main__":
    main()
