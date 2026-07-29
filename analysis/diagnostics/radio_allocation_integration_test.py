#!/usr/bin/env python3
"""Source-bound regression for fail-closed RadioLib allocation."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
PLATFORMIO = ROOT / "firmware" / "platformio.ini"
LORAWAN = ROOT / "firmware" / "src" / "lorawan.cpp"
MESH_DIAG = ROOT / "firmware" / "src" / "main_meshtastic_diag.cpp"
DECODER = ROOT / "analysis" / "diagnostics" / "decode_flight_state.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    ini = PLATFORMIO.read_text(encoding="utf-8")
    source = LORAWAN.read_text(encoding="utf-8")
    mesh_diag = MESH_DIAG.read_text(encoding="utf-8")
    decoder = DECODER.read_text(encoding="utf-8")

    base_flags = ini.split("[env:stratolink_soak]", 1)[0]
    require("-fcheck-new" in base_flags, "base flight graph lacks -fcheck-new")
    require(
        "new STM32WLx(new STM32WLx_Module())" not in source,
        "nested unchecked RadioLib allocation remains",
    )
    require(
        re.search(r"STM32WLx_Module\* module = new STM32WLx_Module\(\);", source)
        is not None,
        "module allocation is not staged",
    )
    require("if (!module || !module->hal)" in source, "module/HAL null gate missing")
    require("STM32WLx* candidate = new STM32WLx(module);" in source, "radio allocation is not staged")
    require("if (!candidate)" in source, "radio null gate missing")
    require("delete module->hal;" in source, "HAL cleanup missing after radio allocation failure")
    require("delete module;" in source, "module cleanup missing")
    require(
        "RADIOLIB_ERR_MEMORY_ALLOCATION_FAILED" in source,
        "allocation error is not recorded",
    )
    require(
        "uint16_t allocation_failures;" in source
        and "allocation_failures\"] == 0" in decoder,
        "allocation failure counter is not exposed to the HIL gate",
    )
    require(
        "if (!radio && !allocate_radio()) return false;" in source,
        "lorawan_init does not fail closed on allocation failure",
    )
    require(
        "static STM32WLx radio =" not in mesh_diag
        and "static STM32WLx* radio = nullptr;" in mesh_diag,
        "Meshtastic diagnostic still allocates RadioLib before setup",
    )
    require(
        "if (!allocate_diag_radio())" in mesh_diag
        and "RADIOLIB_ERR_MEMORY_ALLOCATION_FAILED" in mesh_diag
        and "if (!radio)" in mesh_diag,
        "Meshtastic diagnostic does not expose and contain allocation failure",
    )
    print("radio allocation integration: PASS")


if __name__ == "__main__":
    main()
