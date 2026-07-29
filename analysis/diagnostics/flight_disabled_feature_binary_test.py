#!/usr/bin/env python3
"""Prove flight-disabled radio features are absent from the linked image.

Raw byte scans are not sufficient here: RadioLib's generic SX1262 modem
implementation contains a 434.0 MHz default constant even when StratoLink's
CTT window is compiled out.  Symbol reachability is the release-relevant
property.
"""

from pathlib import Path
import os
import re
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[2]
CONFIG = (ROOT / "firmware/include/config.h").read_text(encoding="utf-8")
BUILD_DIR = Path(
    os.environ.get("STRATOLINK_BUILD_DIR", ROOT / "firmware/.pio/build")
).resolve()
FLIGHT_ELF = BUILD_DIR / "stratolink/firmware.elf"
CTT_DIAG_ELF = BUILD_DIR / "ctt_diag/firmware.elf"
CTT_TX_DIAG_ELF = BUILD_DIR / "ctt_tx_diag/firmware.elf"


def bool_macro(name: str) -> bool:
    match = re.search(
        rf"^#define\s+{re.escape(name)}\s+(true|false)\s*$",
        CONFIG,
        re.MULTILINE,
    )
    assert match, f"missing boolean macro {name}"
    return match.group(1) == "true"


def find_nm() -> str:
    direct = shutil.which("arm-none-eabi-nm")
    if direct:
        return direct

    platformio_home = Path(os.environ.get("PLATFORMIO_CORE_DIR", Path.home() / ".platformio"))
    matches = sorted(platformio_home.glob("packages/**/arm-none-eabi-nm"))
    assert matches, "arm-none-eabi-nm not found; install the PlatformIO ARM toolchain"
    return str(matches[0])


def symbols(nm: str, elf: Path) -> str:
    assert elf.is_file(), f"missing linked image: {elf}"
    return subprocess.run(
        [nm, "-C", "--defined-only", str(elf)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


assert not bool_macro("CTT_LISTEN_ENABLE"), (
    "StratoLink-2 uses the high-band RAK3172-9-SM-NI; CTT must remain disabled "
    "until an exact 434 MHz receive path is qualified"
)

nm = find_nm()
flight = symbols(nm, FLIGHT_ELF)
ctt_diag = symbols(nm, CTT_DIAG_ELF)
ctt_tx_diag = symbols(nm, CTT_TX_DIAG_ELF)

assert "lorawan_ctt_window(unsigned long, unsigned short)" not in flight, (
    "CTT listener is reachable in the flight ELF despite CTT_LISTEN_ENABLE=false"
)
assert "lorawan_ctt_window(unsigned long, unsigned short)" in ctt_diag, (
    "CTT diagnostic no longer contains the listener; the absence check may be vacuous"
)
assert "ctt_tx_diag_state" not in flight, (
    "finite CTT transmitter diagnostic is reachable in the flight ELF"
)
assert "ctt_tx_diag_state" in ctt_tx_diag, (
    "CTT transmitter diagnostic state is missing; the flight absence check may be vacuous"
)
assert "lorawan_relay_window(unsigned long, unsigned short, bool)" in flight, (
    "flight ELF unexpectedly lost the supported high-band shared relay window"
)

print(
    "PASS: CTT receiver/transmitter diagnostics are present in their own images "
    "and absent from the flight ELF"
)
