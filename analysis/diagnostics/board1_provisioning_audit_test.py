#!/usr/bin/env python3
"""Exercise missing/duplicate provisioning, profile mismatch, and redaction."""

from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile

from board1_provisioning_audit import ROOT, audit


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="stratolink-provision-test-") as temp:
        root = Path(temp)
        include = root / "firmware/include"
        include.mkdir(parents=True)
        (root / "firmware/src").mkdir()
        for relative in ("firmware/platformio.ini", "firmware/src/lorawan.cpp",
                         "firmware/include/config.h", "firmware/include/device_identity.h"):
            shutil.copyfile(ROOT / relative, root / relative)
        header = include / "secrets_board1.h"
        active = include / "secrets.h"
        active.symlink_to(header.name)
        euids = [f"A00000000000000{i}" for i in range(1, 5)]
        key = "1234567890ABCDEF" * 2
        definitions = ['#define LORAWAN_APP_EUI "0000000000000000"',
                       f'#define B2B_FLEET_KEY "{key}"']
        for region, eui in zip(("US", "EU", "AS", "AU"), euids):
            definitions.extend((f'#define LORAWAN_DEV_EUI_{region} "{eui}"',
                                f'#define LORAWAN_APP_KEY_{region} "{key}"'))
        complete = "\n".join(definitions) + "\n"
        header.write_text(complete)
        passed = audit(root)
        assert passed["passed"], passed["failures"]
        rendered = json.dumps(passed)
        assert key not in rendered and all(eui not in rendered for eui in euids)

        header.write_text(complete.replace(f'#define B2B_FLEET_KEY "{key}"', ""))
        assert not audit(root)["b2b_fleet_key_valid"]
        header.write_text(complete.replace(euids[1], euids[0]))
        assert not audit(root)["present_regional_device_euis_unique"]
        header.write_text(complete.replace(f'#define LORAWAN_DEV_EUI_AU "{euids[3]}"', ""))
        assert not audit(root)["regions"]["AU"]["device_eui_valid"]
        header.write_text(complete.replace(key, "0" * 32))
        assert not audit(root)["b2b_fleet_key_valid"]
        header.write_text(complete + f"\n#error {key}\n")
        rejected = subprocess.run(
            [sys.executable, str(ROOT / "analysis/diagnostics/board1_provisioning_audit.py"),
             "--root", str(root)], text=True, capture_output=True, check=False,
        )
        assert rejected.returncode == 1
        assert key not in rejected.stdout + rejected.stderr
        assert not json.loads(rejected.stdout)["passed"]
        header.write_text(complete)
        other = include / "secrets_board2.h"
        shutil.copyfile(header, other)
        active.unlink()
        active.symlink_to(other.name)
        assert not audit(root)["board1_header_selected"]
        active.unlink()
        active.symlink_to(header.name)
        ini = root / "firmware/platformio.ini"
        ini.write_text(ini.read_text().replace("build_flags =", "build_flags =\n    -D BENCH_SEED_REGION", 1))
        assert not audit(root)["passed"]
    print("PASS: Board1 provisioning rejects missing/duplicate/zero credentials and wrong profile; output is redacted")


if __name__ == "__main__":
    main()
