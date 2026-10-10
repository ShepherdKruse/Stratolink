#!/usr/bin/env python3
"""Host tests for the no-reset StratoLink-1 baseline capture."""

from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest

from preserve_board1_baseline import (
    FLASH_ADDRESS,
    FLASH_BYTES,
    FORENSIC_DEVICE,
    RAM_ADDRESS,
    TAMP_ADDRESS,
    artifact_paths,
    build_commander_script,
    build_jlink_script,
    identify_candidate_prefixes,
    require_create_once,
    transcript_metadata,
)


SCRIPT = Path(__file__).with_name("preserve_board1_baseline.py")
FAKE_JLINK = r'''#!/usr/bin/env python3
import json
import os
from pathlib import Path
import signal
import sys
import time

sys.stdout.reconfigure(line_buffering=True)
args = sys.argv[1:]
option = lambda name: args[args.index(name) + 1]
assert option("-device") == "Cortex-M4"
assert option("-SelectEmuBySN") == "802007563"
assert option("-if") == "SWD"
settings = Path(option("-JLinkScriptFile")).read_text()
assert 'JLINK_ExecCommand("InhibitConnectRetries = 1")' in settings
commands = Path(option("-CommanderScript")).read_text().splitlines()
commands = [line.strip() for line in commands if line.strip()]
cleanup = not any(line.startswith("savebin ") for line in commands)
mode = os.environ["FAKE_JLINK_MODE"]
events = Path(os.environ["FAKE_JLINK_EVENTS"])
prior_alive = False
if events.exists():
    for event in map(json.loads, events.read_text().splitlines()):
        try:
            os.kill(event["pid"], 0)
            prior_alive = True
        except ProcessLookupError:
            pass
with events.open("a") as handle:
    handle.write(json.dumps({"pid": os.getpid(), "cleanup": cleanup,
                            "prior_alive": prior_alive, "commands": commands}) + "\n")
if cleanup:
    assert commands == ["connect", "g", "exit"]
assert all(line.split()[0].lower() in
           {"connect", "h", "exitonerror", "savebin", "mem32", "g", "exit"}
           for line in commands)
exit_on_error = option("-ExitOnError") == "1"
print("VTref=3.335V")
for command in commands:
    name = command.split()[0].lower()
    if mode == "no_run" and name == "g":
        continue
    print("J-Link>" + command)
    if name == "exitonerror":
        exit_on_error = command.split()[1] == "1"
    elif name == "connect":
        print("J-Link connection not established yet but required for command.")
        if mode == "no_connect":
            print("Cannot connect to the target device.")
            if exit_on_error:
                sys.exit(1)
        else:
            print("Cortex-M4 identified.")
        if mode == "reset":
            print("Attach to CPU failed. Executing connect under reset.")
        if mode == "reset_pin":
            print("Connect failed. Resetting via Reset pin and trying again.")
        if mode == "reset_device":
            print("Reset: Reset device via AIRCR.SYSRESETREQ.")
        if mode == "mutation":
            print("Programming flash")
    elif name == "h":
        print("PC = 08009374, CycleCnt = 6B7D59E2")
    elif name == "savebin":
        _, destination, address, size = command.split()
        value = b"\0" * int(size, 0)
        if "timeout" in mode or mode in ("read_failure", "partial", "early_exit"):
            value = b"bad"
        if not (mode == "missing_flash" and address == "0x08000000"):
            Path(destination).write_bytes(value)
        if "timeout" in mode:
            print("Reading memory...")
            time.sleep(5)
        if mode.startswith("interrupt"):
            os.kill(os.getppid(), signal.SIGINT)
            time.sleep(5)
        if mode == "early_exit":
            sys.exit(3)
        if mode in ("read_failure", "read_failure_full"):
            print("Reading memory...Could not read memory.")
            if exit_on_error:
                print("Script processing completed.")
                print("****** Error: Could not start CPU core. (ErrorCode: -1)")
                sys.exit(0)
    elif name == "mem32" and mode != "missing_tamp":
        for offset in range(0, 80, 16):
            print(f"{0x4000B100 + offset:08X} = 00000000 00000000 00000000 00000000")
    elif name == "g":
        if cleanup and mode == "interrupt_cleanup":
            os.kill(os.getppid(), signal.SIGINT)
            time.sleep(5)
        if mode == "cpu_not_halted":
            print("CPU is not halted !")
        if mode == "plain_connection_failure":
            print("Connection not established")
        if cleanup and mode == "timeout_cleanup":
            time.sleep(5)
        if mode == "failed_resume" or (cleanup and mode == "timeout_failed_resume"):
            print("****** Error: Could not start CPU core. (ErrorCode: -1)")
print("Script processing completed.")
'''


class WrapperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="board1-baseline-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        fake = self.root / "JLinkExe"
        fake.write_text(FAKE_JLINK, encoding="utf-8")
        fake.chmod(0o755)
        self.events = self.root / "events.jsonl"
        self.prefix = self.root / "capture"
        self.paths = artifact_paths(self.prefix)

    def run_wrapper(self, mode: str, *arguments: str) -> subprocess.CompletedProcess[str]:
        environment = dict(os.environ)
        environment.update(
            PATH=str(self.root) + os.pathsep + environment["PATH"],
            FAKE_JLINK_MODE=mode,
            FAKE_JLINK_EVENTS=str(self.events),
        )
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--prefix", str(self.prefix), *arguments],
            env=environment, text=True, capture_output=True, timeout=8, check=False,
        )

    def call_events(self) -> list[dict]:
        return [json.loads(line) for line in self.events.read_text().splitlines()]

    def failure(self, result: subprocess.CompletedProcess[str]) -> dict:
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertFalse(self.paths["manifest"].exists())
        failure_path = self.prefix.with_name("capture_failure.json")
        self.assertTrue(failure_path.is_file(), result.stderr)
        value = json.loads(failure_path.read_text())
        self.assertFalse(value["passed"])
        return value

    def test_read_failure_still_executes_resume_without_retry(self) -> None:
        result = self.run_wrapper("read_failure", "--max-attempts", "3",
                                  "--retry-interval-seconds", "0.1")
        raw = self.prefix.with_name("capture_attempt0001_raw.txt").read_text()
        self.assertIn("J-Link>g\n", raw)
        self.failure(result)
        self.assertEqual(len(self.call_events()), 1)

    def test_zero_exit_read_failure_cannot_publish_success(self) -> None:
        self.failure(self.run_wrapper("read_failure_full"))

    def test_failed_resume_cannot_publish_success(self) -> None:
        self.failure(self.run_wrapper("failed_resume"))

    def test_cpu_not_halted_invalidates_capture_even_with_zero_exit(self) -> None:
        report = self.failure(self.run_wrapper("cpu_not_halted"))
        self.assertIn("cpu is not halted", report["attempts"][0]["command_failure_markers"])

    def test_benign_preamble_cannot_hide_later_connection_failure(self) -> None:
        self.failure(self.run_wrapper("plain_connection_failure"))

    def test_missing_run_evidence_cannot_publish_success(self) -> None:
        self.failure(self.run_wrapper("no_run"))

    def test_capture_validation_failures_are_recorded(self) -> None:
        for mode in ("partial", "missing_flash", "missing_tamp"):
            with self.subTest(mode=mode):
                self.prefix = self.root / mode
                self.paths = artifact_paths(self.prefix)
                result = self.run_wrapper(mode, "--max-attempts", "3")
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.paths["manifest"].exists())
                report = self.prefix.with_name(mode + "_failure.json")
                self.assertTrue(report.is_file(), result.stderr)
                self.assertFalse(json.loads(report.read_text())["passed"])
        self.assertEqual(len(self.call_events()), 3)

    def test_timeout_kills_capture_before_one_bounded_cleanup(self) -> None:
        result = self.run_wrapper("timeout", "--timeout-seconds", "1",
                                  "--cleanup-timeout-seconds", "1",
                                  "--max-attempts", "3")
        report = self.failure(result)
        calls = self.call_events()
        self.assertEqual([call["cleanup"] for call in calls], [False, True])
        self.assertFalse(calls[1]["prior_alive"])
        attempt = report["attempts"][0]
        self.assertTrue(attempt["timed_out"])
        self.assertTrue(attempt["cleanup"]["resume_command_seen"])
        self.assertFalse(attempt["cleanup"]["resume_verified"])

    def test_cleanup_timeout_is_bounded_and_recorded(self) -> None:
        report = self.failure(self.run_wrapper(
            "timeout_cleanup", "--timeout-seconds", "1",
            "--cleanup-timeout-seconds", "1"))
        self.assertTrue(report["attempts"][0]["cleanup"]["timed_out"])
        self.assertEqual(len(self.call_events()), 2)

    def test_cleanup_resume_error_is_recorded(self) -> None:
        report = self.failure(self.run_wrapper(
            "timeout_failed_resume", "--timeout-seconds", "1",
            "--cleanup-timeout-seconds", "1"))
        self.assertFalse(report["attempts"][0]["cleanup"]["passed"])
        self.assertEqual(len(self.call_events()), 2)

    def test_early_exit_after_halt_attempts_cleanup(self) -> None:
        self.failure(self.run_wrapper("early_exit"))
        calls = self.call_events()
        self.assertEqual([call["cleanup"] for call in calls], [False, True])
        self.assertFalse(calls[1]["prior_alive"])

    def test_interrupt_reaps_capture_before_one_cleanup(self) -> None:
        report = self.failure(self.run_wrapper("interrupt"))
        self.assertTrue(report["attempts"][0]["interrupted"])
        calls = self.call_events()
        self.assertEqual([call["cleanup"] for call in calls], [False, True])
        self.assertFalse(calls[1]["prior_alive"])

    def test_second_interrupt_stops_cleanup_without_another_attempt(self) -> None:
        report = self.failure(self.run_wrapper("interrupt_cleanup"))
        self.assertTrue(report["attempts"][0]["cleanup"]["interrupted"])
        self.assertEqual(len(self.call_events()), 2)

    def test_no_connection_stops_without_cleanup_or_memory_commands(self) -> None:
        self.failure(self.run_wrapper("no_connect"))
        self.assertEqual(len(self.call_events()), 1)
        raw = self.prefix.with_name("capture_attempt0001_raw.txt").read_text()
        self.assertNotIn("J-Link>h", raw)
        self.assertNotIn("J-Link>g", raw)

    def test_complete_capture_retains_create_once_and_serial_guard(self) -> None:
        result = self.run_wrapper("success")
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(self.paths["manifest"].read_text())
        self.assertEqual(value["artifacts"]["flash"]["bytes"], 262144)
        self.assertEqual(value["artifacts"]["ram"]["bytes"], 65536)
        self.assertEqual(value["artifacts"]["tamp"]["bytes"], 80)
        self.assertTrue(value["target"].get("resume_command_seen"))
        self.assertFalse(value["target"]["resume_verified"])
        before = self.paths["manifest"].read_bytes()
        self.assertNotEqual(self.run_wrapper("success").returncode, 0)
        self.assertEqual(self.paths["manifest"].read_bytes(), before)
        self.prefix = self.root / "wrong_serial"
        self.assertNotEqual(self.run_wrapper("success", "--jlink-serial", "other").returncode, 0)
        self.assertEqual(len(self.call_events()), 1)

    def test_reset_and_mutation_markers_remain_fatal(self) -> None:
        for mode in ("reset", "reset_pin", "reset_device", "mutation"):
            with self.subTest(mode=mode):
                self.prefix = self.root / mode
                self.paths = artifact_paths(self.prefix)
                result = self.run_wrapper(mode)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.paths["manifest"].exists())
                self.assertTrue(self.prefix.with_name(mode + "_failure.json").is_file())


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        prefix = root / "board1"
        paths = artifact_paths(prefix)
        command = build_commander_script(paths)
        target = build_jlink_script()
        assert command.index("\nh\n") < command.index("savebin")
        assert command.index(f"0x{RAM_ADDRESS:08X}") < command.index(
            f"mem32 0x{TAMP_ADDRESS:08X} 0x14"
        )
        assert command.index("mem32") < command.index("0x58004020")
        assert command.index("0x58004020") < command.index(
            f"0x{FLASH_ADDRESS:08X} 0x{FLASH_BYTES:08X}"
        )
        assert command.index("savebin", command.index("0x58004020")) < command.index("\ng\n")
        assert "InhibitConnectRetries = 1" in target
        assert "SetRestartOnClose = 1" in target
        assert FORENSIC_DEVICE == "Cortex-M4"

        normal = transcript_metadata(
            "J-Link connection not established yet but required for command.\n"
            "VTref=3.335V\nCortex-M4 identified.\n"
            "J-Link>h\nJ-Link>savebin ram 0x20000000 0x10000\n"
            "J-Link>mem32 0x4000B100 0x14\nJ-Link>savebin optr 0x58004020 4\n"
            "J-Link>savebin flash 0x08000000 0x40000\nJ-Link>g\nJ-Link>exit\n"
            "Script processing completed.\n",
            0,
        )
        assert normal["passed"] is True
        assert normal["vtref_v"] == 3.335
        reset = transcript_metadata(
            "J-Link connection not established yet but required for command.\n"
            "Attach to CPU failed. Executing connect under reset.\n"
            "Cortex-M4 identified.\nScript processing completed.\n",
            1,
        )
        assert reset["passed"] is False
        assert reset["connect_under_reset_marker"] is True
        authorized_reset = transcript_metadata(
            "J-Link connection not established yet but required for command.\n"
            "Attach to CPU failed. Executing connect under reset.\n"
            "Cortex-M4 identified.\nJ-Link>g\nJ-Link>exit\nScript processing completed.\n",
            0,
            development_reset_attach=True,
            require_capture=False,
        )
        assert authorized_reset["passed"] is True
        assert authorized_reset["connection_failure_markers"] == []
        mutating = transcript_metadata("Mass erase requested\n", 1)
        assert mutating["mutation_markers"] == ["mass erase"]

        capture = root / "capture.bin"
        capture.write_bytes(b"candidate" + b"\xff" * 32)
        candidates = root / "candidates"
        (candidates / "v1").mkdir(parents=True)
        (candidates / "v2").mkdir(parents=True)
        (candidates / "v1/firmware.bin").write_bytes(b"candidate")
        (candidates / "v2/firmware.bin").write_bytes(b"different")
        matches = identify_candidate_prefixes(capture, candidates)
        assert [match["candidate"] for match in matches] == ["v1"]

        require_create_once(prefix, paths)
        paths["manifest"].write_text("occupied", encoding="utf-8")
        try:
            require_create_once(prefix, paths)
        except SystemExit as error:
            assert "refusing to overwrite" in str(error)
        else:
            raise AssertionError("create-once collision was accepted")

    print("PASS: Board-1 capture is create-once and requests reset retry inhibition")


if __name__ == "__main__":
    main()
    unittest.main()
