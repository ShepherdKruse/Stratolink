#!/usr/bin/env python3
"""Merge only six verified Board1 regional macros; read-only dry-run by default.

No network or hardware operations. --apply is a separately authorized local
provisioning action: retain the private backup and never publish header content,
compiler output, or generated firmware. Operators must exclude other header
editors; advisory locks and final rechecks cannot lock non-cooperating writers.
"""

from __future__ import annotations

import argparse
import configparser
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import tempfile

from board1_provisioning_audit import FEATURES, FORBIDDEN_FLAGS, ROOT
from provision_board1_ttn_regions import DEFAULT_STATE, SCHEMA, TARGETS

REGIONS = ("EU", "AS", "AU")
NEW_NAMES = tuple(f"LORAWAN_{kind}_{region}" for region in REGIONS
                  for kind in ("DEV_EUI", "APP_KEY"))
PRESERVED = ("LORAWAN_DEV_EUI", "LORAWAN_APP_KEY", "LORAWAN_DEV_EUI_US",
             "LORAWAN_APP_KEY_US", "LORAWAN_APP_EUI", "B2B_FLEET_KEY",
             "CMD_BALLOON_ID", "RELAY_SOLAR_MIN_MV", *FEATURES)


class Stop(RuntimeError):
    """Only fixed messages, never credential values or compiler diagnostics."""


def signature(info, data: bytes) -> tuple:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns,
            hashlib.sha256(data).digest())


def private_snapshot(path: Path) -> tuple[bytes, tuple]:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        raise Stop("private input must be an accessible regular file") from None
    with os.fdopen(fd, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise Stop("private input must be a single-link regular file")
        if stat.S_IMODE(info.st_mode) != 0o600:
            raise Stop("private input must have mode 0600")
        data = handle.read()
        final_info = os.fstat(handle.fileno())
        if signature(info, data) != signature(final_info, data) or len(data) != info.st_size:
            raise Stop("private input changed while being read")
        return data, signature(info, data)


def private_bytes(path: Path) -> bytes:
    return private_snapshot(path)[0]


def snapshot(path: Path) -> tuple:
    info = path.lstat()
    return signature(info, path.read_bytes())


def selector(root: Path) -> None:
    for directory in (root, root / "firmware", root / "firmware/include"):
        if directory.is_symlink() or not directory.is_dir():
            raise Stop("header directory/selector anomaly")
    active = root / "firmware/include/secrets.h"
    if not active.is_symlink() or os.readlink(active) != "secrets_board1.h":
        raise Stop("selector must remain the relative Board1 symlink")


def checkpoint_values(data: bytes) -> dict:
    def unique_pairs(pairs):
        result = {}
        for name, value in pairs:
            if name in result:
                raise Stop("checkpoint has duplicate JSON fields")
            result[name] = value
        return result
    try:
        state = json.loads(data, object_pairs_hook=unique_pairs)
    except (ValueError, UnicodeError):
        raise Stop("checkpoint JSON is malformed") from None
    if not isinstance(state, dict) or state.get("schema") != SCHEMA:
        raise Stop("checkpoint schema mismatch")
    if state.get("targets") != list(TARGETS):
        raise Stop("checkpoint targets mismatch")
    identities = state.get("identities")
    if not isinstance(identities, dict) or set(identities) != set(REGIONS):
        raise Stop("checkpoint identities must be exactly EU/AS/AU")
    result = {}
    for region in REGIONS:
        identity = identities[region]
        if not isinstance(identity, dict) or identity.get("allocation_started") is not True:
            raise Stop("checkpoint allocation proof is missing")
        if identity.get("registrations") != dict.fromkeys(("is", "js", "ns", "as"), "verified"):
            raise Stop("all twelve checkpoint registries must be verified")
        for kind, field, count in (("DEV_EUI", "dev_eui", 16), ("APP_KEY", "app_key", 32)):
            value = identity.get(field)
            if not isinstance(value, str) or not re.fullmatch(f"[0-9A-F]{{{count}}}", value) or int(value, 16) == 0:
                raise Stop("checkpoint credentials must be nonzero canonical hex")
            result[f"LORAWAN_{kind}_{region}"] = value
    for kind in ("DEV_EUI", "APP_KEY"):
        if len({result[f"LORAWAN_{kind}_{region}"] for region in REGIONS}) != 3:
            raise Stop("checkpoint regional credentials must be distinct")
    return result


def flight_flags(root: Path) -> list[str]:
    if any(os.environ.get(name) for name in (
            "PLATFORMIO_BUILD_FLAGS", "PLATFORMIO_BUILD_UNFLAGS", "PLATFORMIO_EXTRA_CONFIGS")):
        raise Stop("external build overrides prevent safe preprocessing")
    config = configparser.ConfigParser(interpolation=None)
    config.read(root / "firmware/platformio.ini")
    section = config["env:stratolink"]
    if section.get("extends") or config.has_option("platformio", "extra_configs"):
        raise Stop("flight build inheritance is outside this helper")
    text = section.get("build_flags", "")
    if "${" in text:
        raise Stop("interpolated build flags are outside this helper")
    tokens = iter(shlex.split(text))
    flags = []
    for token in tokens:
        if token.startswith(("-include", "-imacros")):
            raise Stop("forced preprocessing inputs are not supported")
        if token in ("-D", "-U"):
            try:
                token += next(tokens)
            except StopIteration:
                raise Stop("incomplete preprocessing flag") from None
        if token.startswith(("-D", "-U")):
            if token[2:].split("=", 1)[0] in FORBIDDEN_FLAGS:
                raise Stop("bench flags are not allowed in flight provisioning")
            flags.append(token)
    return flags


def effective(root: Path, header: bytes) -> dict:
    source = (root / "firmware/src/lorawan.cpp").read_text()
    start = source.index("#ifndef LORAWAN_DEV_EUI_US")
    end = source.index("typedef struct", start)
    translation = header.decode() + '\n#include "device_identity.h"\n' + source[start:end]
    translation += "\n" + "\n".join(f"AUDIT_{name} {name}" for name in (*PRESERVED, *NEW_NAMES))
    result = subprocess.run(
        ["c++", "-E", "-P", "-x", "c++", "-I", str(root / "firmware/include"),
         *flight_flags(root), "-"], input=translation, text=True, capture_output=True,
        timeout=15, check=False)
    if result.returncode:
        raise Stop("effective preprocessing failed; diagnostics withheld")
    values = dict(re.findall(r"^AUDIT_(\w+)\s+(.+)$", result.stdout, re.M))
    if set(values) != set((*PRESERVED, *NEW_NAMES)):
        raise Stop("effective preprocessing fields incomplete")
    return values


def hex_literal(value: str, length: int) -> str:
    match = re.fullmatch(f'"([0-9a-fA-F]{{{length}}})"', value)
    if not match or int(match[1], 16) == 0:
        raise Stop("existing private identity is invalid")
    return match[1].upper()


def fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def merge(root: Path = ROOT, checkpoint: Path = DEFAULT_STATE, apply: bool = False) -> dict:
    root, checkpoint = Path(root).absolute(), Path(checkpoint).absolute()
    selector(root)
    header = root / "firmware/include/secrets_board1.h"
    original, header_signature = private_snapshot(header)
    private = checkpoint.parent
    if private.is_symlink() or not private.is_dir() or stat.S_IMODE(private.stat().st_mode) != 0o700:
        raise Stop("checkpoint directory must be real and mode 0700")
    checkpoint_data, checkpoint_signature = private_snapshot(checkpoint)
    values = checkpoint_values(checkpoint_data)
    guard = re.search(rb"(?m)^[ \t]*#endif(?:[ \t]*//[^\r\n]*)?[ \t]*(?:\r?\n)?\Z", original)
    if not guard or len(re.findall(rb"(?m)^\s*#endif\b", original)) != 1 or \
            len(re.findall(rb"(?m)^\s*#ifndef\s+SECRETS_H\s*$", original)) != 1 or \
            len(re.findall(rb"(?m)^\s*#define\s+SECRETS_H\s*$", original)) != 1:
        raise Stop("expected single final SECRETS_H guard")
    for name in NEW_NAMES:
        if re.search(rb"\b" + name.encode() + rb"\b", original):
            raise Stop("regional macro already present; do not overwrite or duplicate")
    newline = "\r\n" if b"\r\n" in original else "\n"
    block = "// Board1 regional identities from verified private checkpoint." + newline
    block += newline.join(f'#define {name} "{values[name]}"' for name in NEW_NAMES) + newline
    candidate = original[:guard.start()] + block.encode() + original[guard.start():]
    tracked = [header, checkpoint, root / "firmware/platformio.ini", root / "firmware/src/lorawan.cpp",
               root / "firmware/include/config.h", root / "firmware/include/device_identity.h"]
    signatures = {path: snapshot(path) for path in tracked if path not in (header, checkpoint)}
    signatures.update({header: header_signature, checkpoint: checkpoint_signature})
    before, after = effective(root, original), effective(root, candidate)
    if any(after[name] != before[name] for name in PRESERVED):
        raise Stop("US, JoinEUI, fleet, command or flight configuration changed")
    if before["LORAWAN_APP_EUI"] != '"0000000000000000"':
        raise Stop("JoinEUI does not match registered shared JoinEUI")
    if int(before["CMD_BALLOON_ID"].rstrip("uUlL"), 0) != 1:
        raise Stop("command address must remain Board1")
    if any(before[name] not in ("1", "true") for name in FEATURES) or \
            int(before["RELAY_SOLAR_MIN_MV"].rstrip("uUlL"), 0) != 3000:
        raise Stop("full flight features and original solar gate are required")
    for name, value in values.items():
        if after[name] != json.dumps(value):
            raise Stop("effective regional macro does not match checkpoint")
    us_eui = hex_literal(before["LORAWAN_DEV_EUI_US"], 16)
    us_key = hex_literal(before["LORAWAN_APP_KEY_US"], 32)
    fleet = hex_literal(before["B2B_FLEET_KEY"], 32)
    if len({us_eui, *(values[f"LORAWAN_DEV_EUI_{r}"] for r in REGIONS)}) != 4 or \
            len({us_key, fleet, *(values[f"LORAWAN_APP_KEY_{r}"] for r in REGIONS)}) != 5:
        raise Stop("regional credentials must remain distinct from US and fleet")
    backup = private / "secrets_board1.before-regions.h"
    if backup.exists() or backup.is_symlink():
        if private_bytes(backup) != original:
            raise Stop("private backup conflicts with original header")

    def unchanged():
        selector(root)
        if any(snapshot(path) != signature for path, signature in signatures.items()):
            raise Stop("header/checkpoint/build input changed during preflight")

    unchanged()
    report = {"schema": "stratolink.board1_header_merge.redacted.v1", "passed": True,
              "mode": "apply" if apply else "dry_run", "header_changed": False,
              "new_macro_count": 6, "effective_regions_verified": ["US", *REGIONS],
              "preserved_US_join_fleet_command": True, "private_backup": str(backup),
              "private_checkpoint": str(checkpoint), "header_sha256_before": hashlib.sha256(original).hexdigest(),
              "header_sha256_candidate": hashlib.sha256(candidate).hexdigest(),
              "network_accessed": False, "hardware_accessed": False}
    if not apply:
        return report
    lock = checkpoint.with_suffix(".lock")
    private_bytes(lock)
    lock_fd = os.open(lock, os.O_RDWR | os.O_NOFOLLOW)
    temporary = None
    try:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Stop("private checkpoint is locked by another operation") from None
        unchanged()
        if not backup.exists():
            fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(original)
                handle.flush()
                os.fsync(handle.fileno())
            fsync_directory(private)
        if private_bytes(backup) != original:
            raise Stop("private backup verification failed")
        with tempfile.NamedTemporaryFile(dir=header.parent, prefix=".board1-regions-", delete=False) as handle:
            temporary = Path(handle.name)
            os.fchmod(handle.fileno(), 0o600)
            handle.write(candidate)
            handle.flush()
            os.fsync(handle.fileno())
        unchanged()
        os.replace(temporary, header)
        temporary = None
        fsync_directory(header.parent)
        selector(root)
        if private_bytes(header) != candidate or private_bytes(checkpoint) != checkpoint_data:
            raise Stop("post-write verification failed; private backup retained; no rollback attempted")
        report["header_changed"] = True
        return report
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        os.close(lock_fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--dry-run", action="store_true", help="read-only default; creates no backup or header")
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_STATE)
    args = parser.parse_args()
    try:
        result = merge(checkpoint=args.checkpoint, apply=args.apply)
    except Stop as error:
        result = {"passed": False, "error": str(error), "write_mode_requested": args.apply}
    except Exception:
        result = {"passed": False, "error": "operation stopped; diagnostics withheld; inspect private state before retry",
                  "write_mode_requested": args.apply}
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
