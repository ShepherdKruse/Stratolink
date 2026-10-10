#!/usr/bin/env python3
"""Read-only, redacted audit of the full-feature Board1 flight configuration.

This checks local provisioning, not TTN registration, RF qualification, or a
flashed binary. Compiler output containing credentials is never emitted.
"""

from __future__ import annotations

import argparse
import configparser
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess


ROOT = Path(__file__).resolve().parents[2]
REGIONS = ("US", "EU", "AS", "AU")
FEATURES = ("GNSS_ENABLE", "CMD_ENABLE", "MESHTASTIC_RELAY_ENABLE",
            "CTT_LISTEN_ENABLE", "B2B_ENABLE")
FORBIDDEN_FLAGS = {"BENCH_SEED_REGION", "B2B_RF_DIAG_BUILD",
                   "STRATOLINK_HIL", "GPS_DIAG_BUILD"}


def audit(root: Path = ROOT) -> dict:
    include = root / "firmware/include"
    active = include / "secrets.h"
    expected = include / "secrets_board1.h"
    ini = root / "firmware/platformio.ini"
    radio = root / "firmware/src/lorawan.cpp"
    failures = []
    board1_selected = active.is_symlink() and active.resolve() == expected.resolve()
    if not board1_selected:
        failures.append("active secrets.h must select secrets_board1.h")
    if not active.is_file():
        raise ValueError("active provisioning header is missing")

    config = configparser.ConfigParser(interpolation=None)
    config.read(ini)
    section = config["env:stratolink"]
    if section.get("extends") or config.has_option("platformio", "extra_configs"):
        raise ValueError("inherited or extra build configuration needs explicit audit support")
    if any(os.environ.get(name) for name in (
        "PLATFORMIO_BUILD_FLAGS", "PLATFORMIO_BUILD_UNFLAGS", "PLATFORMIO_EXTRA_CONFIGS"
    )):
        raise ValueError("external PlatformIO overrides prevent a source-only provisioning audit")
    flag_text = section.get("build_flags", "")
    if "${" in flag_text:
        raise ValueError("interpolated flight flags need explicit audit support")
    tokens = shlex.split(flag_text)
    cpp_flags = []
    define_names = []
    for index, token in enumerate(tokens):
        if token in ("-D", "-U"):
            if index + 1 == len(tokens):
                raise ValueError("incomplete flight define flag")
            cpp_flags.extend((token, tokens[index + 1]))
            if token == "-D":
                define_names.append(tokens[index + 1].split("=", 1)[0])
        elif token.startswith(("-D", "-U")):
            cpp_flags.append(token)
            if token.startswith("-D"):
                define_names.append(token[2:].split("=", 1)[0])
        elif token.startswith(("-include", "-imacros")):
            raise ValueError("forced header inputs need explicit audit support")
    if FORBIDDEN_FLAGS.intersection(define_names):
        failures.append("flight environment contains a bench or diagnostic define")

    # Apply the driver's actual compatibility fallbacks instead of maintaining
    # a second credential-resolution policy in this audit.
    source = radio.read_text(encoding="utf-8")
    start = source.index("#ifndef LORAWAN_DEV_EUI_US")
    end = source.index("typedef struct", start)
    names = ["LORAWAN_APP_EUI", "B2B_FLEET_KEY", "CMD_BALLOON_ID",
             "RELAY_SOLAR_MIN_MV", *FEATURES]
    names += [f"LORAWAN_{kind}_{region}" for region in REGIONS
              for kind in ("DEV_EUI", "APP_KEY")]
    translation = '#include "device_identity.h"\n' + source[start:end] + "\n"
    translation += "\n".join(f"AUDIT_{name} {name}" for name in names)
    result = subprocess.run(
        ["c++", "-E", "-P", "-x", "c++", "-I", str(include), *cpp_flags, "-"],
        input=translation, text=True, capture_output=True, timeout=15, check=False,
    )
    if result.returncode:
        # Compiler diagnostics can quote source keys; never forward them.
        raise ValueError("provisioning preprocessing failed; compiler diagnostics withheld")
    values = dict(re.findall(r"^AUDIT_(\w+)\s+(.+)$", result.stdout, re.M))

    def hex_value(name: str, length: int, allow_zero: bool = False) -> str | None:
        match = re.fullmatch(r'"([0-9a-fA-F]+)"', values.get(name, ""))
        value = match[1].upper() if match else ""
        return value if len(value) == length and (allow_zero or int(value, 16)) else None

    regions = {}
    identities = []
    for region in REGIONS:
        eui = hex_value(f"LORAWAN_DEV_EUI_{region}", 16)
        key = hex_value(f"LORAWAN_APP_KEY_{region}", 32)
        regions[region] = {"device_eui_valid": bool(eui), "application_key_valid": bool(key)}
        if not eui or not key:
            failures.append(f"{region} regional identity is missing or malformed")
        if eui:
            identities.append(eui)
    unique = len(identities) == len(set(identities))
    if not unique:
        failures.append("regional device identities are duplicated")
    join_valid = hex_value("LORAWAN_APP_EUI", 16, allow_zero=True) is not None
    if not join_valid:
        failures.append("JoinEUI is missing or malformed")
    fleet_valid = hex_value("B2B_FLEET_KEY", 32) is not None
    if not fleet_valid:
        failures.append("B2B fleet key is absent, zero, or not a 128-bit hex literal")
    features = {name: values.get(name) in ("true", "1") for name in FEATURES}
    if not all(features.values()):
        failures.append("one or more intended flight features are disabled or unresolved")
    try:
        balloon_id = int(values.get("CMD_BALLOON_ID", "").rstrip("uUlL"), 0)
        solar_floor = int(values.get("RELAY_SOLAR_MIN_MV", "").rstrip("uUlL"), 0)
    except ValueError:
        raise ValueError("command identity or solar gate is not a supported integer literal") from None
    if balloon_id != 1:
        failures.append("command/B2B address is not Board1")
    if solar_floor <= 0:
        failures.append("flight solar gate is relaxed")
    paths = [ini, radio, include / "config.h", include / "device_identity.h", active]
    return {
        "schema": "stratolink.board1_provisioning_audit.v1",
        "passed": not failures,
        "scope": "local full-feature provisioning only; no network or target access, no credential values",
        "environment": "stratolink",
        "board1_header_selected": board1_selected,
        "active_header_target": active.resolve().name,
        "build_define_names": sorted(set(define_names)),
        "features": features,
        "command_balloon_id": balloon_id,
        "relay_solar_floor_mv": solar_floor,
        "regions": regions,
        "present_regional_device_euis_unique": unique,
        "join_eui_valid": join_valid,
        "b2b_fleet_key_valid": fleet_valid,
        "source_sha256": {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in paths},
        "failures": failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        report = audit(args.root.resolve())
    except (OSError, ValueError, KeyError, configparser.Error, subprocess.TimeoutExpired):
        # Even an exception from a malformed secret must remain redacted.
        report = {"passed": False, "failures": ["audit inputs could not be resolved safely"]}
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
