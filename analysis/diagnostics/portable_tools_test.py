#!/usr/bin/env python3
"""Check baseline capture can start without a historical candidate checkout."""

from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

import ctt_two_node_hil
import generate_flight_hil


HERE = Path(__file__).resolve().parent


def main() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        for name in ("preserve_board1_baseline.py", "decode_flight_state.py",
                     "evidence_provenance.py"):
            shutil.copyfile(HERE / name, root / name)
        result = subprocess.run(
            [sys.executable, str(root / "preserve_board1_baseline.py"), "--help"],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode == 0, result.stderr
        assert "--development-reset-attach" in result.stdout
        toolchain = root / "custom-pio/packages/toolchain-gccarmnoneeabi/bin"
        toolchain.mkdir(parents=True)
        nm = toolchain / "arm-none-eabi-nm"
        nm.touch()
        with patch.dict(os.environ, {"PLATFORMIO_CORE_DIR": str(root / "custom-pio")}), \
                patch("shutil.which", return_value=None):
            for module in (ctt_two_node_hil, generate_flight_hil):
                assert module.find_nm() == str(nm), module.__name__
    print("PASS: standalone baseline capture and configurable PlatformIO toolchain")


if __name__ == "__main__":
    main()
