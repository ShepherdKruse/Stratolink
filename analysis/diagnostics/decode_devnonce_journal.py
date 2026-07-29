#!/usr/bin/env python3
"""Decode and compare the two-page STM32 DevNonce flash journal."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import struct
import tempfile

from evidence_provenance import record as provenance_record
from flash_flight_candidate import verify_file_record
from verify_flight_candidate import EXPECTED_BIN_SHA256


EXPECTED_JLINK_SERIAL = "802007563"


PAGE_BYTES = 0x800
JOURNAL_BYTES = 2 * PAGE_BYTES
RECORD_BYTES = 8
RECORDS_PER_PAGE = PAGE_BYTES // RECORD_BYTES
RECORD_TAG = 0x534C0000


def decode_record(data: bytes) -> int | None:
    record = struct.unpack("<Q", data)[0]
    value = record & 0xFFFFFFFF
    check = record >> 32
    if value & 0xFFFF0000 != RECORD_TAG or check != ((~value) & 0xFFFFFFFF):
        return None
    return value & 0xFFFF


def decode(path: Path) -> dict:
    data = path.read_bytes()
    if len(data) != JOURNAL_BYTES:
        raise SystemExit(
            f"{path}: expected {JOURNAL_BYTES} bytes, observed {len(data)}"
        )
    pages = []
    valid_values: list[int] = []
    invalid_slots: list[dict[str, int]] = []
    blank_count = 0
    for page_index in range(2):
        page_valid: list[dict[str, int]] = []
        page_invalid: list[int] = []
        first_blank: int | None = None
        for slot in range(RECORDS_PER_PAGE):
            offset = page_index * PAGE_BYTES + slot * RECORD_BYTES
            raw = data[offset:offset + RECORD_BYTES]
            if raw == b"\xff" * RECORD_BYTES:
                blank_count += 1
                if first_blank is None:
                    first_blank = slot
                continue
            nonce = decode_record(raw)
            if nonce is None:
                page_invalid.append(slot)
                invalid_slots.append({"page": page_index, "slot": slot})
            else:
                page_valid.append({"slot": slot, "nonce": nonce})
                valid_values.append(nonce)
        pages.append(
            {
                "page": page_index,
                "valid_records": page_valid,
                "invalid_slots": page_invalid,
                "first_blank_slot": first_blank,
            }
        )
    highest = max(valid_values) if valid_values else None
    duplicate_values = sorted(
        value for value in set(valid_values) if valid_values.count(value) > 1
    )
    monotonic_unique = (
        len(valid_values) == len(set(valid_values))
        and sorted(valid_values) == list(range(min(valid_values), max(valid_values) + 1))
        if valid_values else True
    )
    return {
        "path": str(path.resolve()),
        "bytes": len(data),
        "valid_record_count": len(valid_values),
        "blank_record_count": blank_count,
        "invalid_record_count": len(invalid_slots),
        "invalid_slots": invalid_slots,
        "highest_nonce": highest,
        "next_nonce": (
            0 if highest is None else highest + 1 if highest < 0xFFFF else None
        ),
        "exhausted": highest == 0xFFFF,
        "duplicate_nonces": duplicate_values,
        "monotonic_unique_sequence": monotonic_unique,
        "pages": pages,
    }


def simulate_advances(before_data: bytes, count: int) -> bytes:
    """Mirror devnonce_next() exactly for a corruption-free journal image."""
    image = bytearray(before_data)
    for _ in range(count):
        page_scans: list[dict[str, int | bool | None]] = []
        for page_index in range(2):
            values: list[int] = []
            first_blank: int | None = None
            for slot in range(RECORDS_PER_PAGE):
                offset = page_index * PAGE_BYTES + slot * RECORD_BYTES
                raw = image[offset:offset + RECORD_BYTES]
                if raw == b"\xff" * RECORD_BYTES:
                    if first_blank is None:
                        first_blank = slot
                    continue
                nonce = decode_record(raw)
                if nonce is None:
                    raise ValueError("cannot simulate a corrupt journal")
                values.append(nonce)
            page_scans.append(
                {
                    "have_valid": bool(values),
                    "max_nonce": max(values) if values else None,
                    "first_blank": first_blank,
                }
            )

        p0, p1 = page_scans
        if p1["have_valid"] and (
            not p0["have_valid"]
            or int(p1["max_nonce"]) > int(p0["max_nonce"])
        ):
            active_page = 1
            previous = int(p1["max_nonce"])
            have_previous = True
        else:
            active_page = 0
            have_previous = bool(p0["have_valid"])
            previous = int(p0["max_nonce"]) if have_previous else 0
        if have_previous and previous == 0xFFFF:
            raise ValueError("DevNonce journal is exhausted")
        next_nonce = previous + 1 if have_previous else 0

        first_blank = page_scans[active_page]["first_blank"]
        if first_blank is None:
            active_page = 1 - active_page
            page_start = active_page * PAGE_BYTES
            image[page_start:page_start + PAGE_BYTES] = b"\xff" * PAGE_BYTES
            first_blank = 0
        offset = active_page * PAGE_BYTES + int(first_blank) * RECORD_BYTES
        value = RECORD_TAG | next_nonce
        record = ((~value) & 0xFFFFFFFF) << 32 | value
        image[offset:offset + RECORD_BYTES] = struct.pack("<Q", record)
    return bytes(image)


def compare(before_path: Path, after_path: Path, expected_advance: int) -> dict:
    before_data = before_path.read_bytes()
    after_data = after_path.read_bytes()
    before = decode(before_path)
    after = decode(after_path)
    failures: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    changed_slots = []
    if len(before_data) == JOURNAL_BYTES and len(after_data) == JOURNAL_BYTES:
        for slot in range(JOURNAL_BYTES // RECORD_BYTES):
            offset = slot * RECORD_BYTES
            left = before_data[offset:offset + RECORD_BYTES]
            right = after_data[offset:offset + RECORD_BYTES]
            if left != right:
                changed_slots.append(
                    {
                        "page": slot // RECORDS_PER_PAGE,
                        "slot": slot % RECORDS_PER_PAGE,
                        "before_blank": left == b"\xff" * RECORD_BYTES,
                        "after_nonce": decode_record(right),
                    }
                )

    require(before["invalid_record_count"] == 0, "before journal is corrupt")
    require(after["invalid_record_count"] == 0, "after journal is corrupt")
    require(before["monotonic_unique_sequence"], "before journal is non-monotonic")
    require(after["monotonic_unique_sequence"], "after journal is non-monotonic")
    require(
        after["valid_record_count"]
        == before["valid_record_count"] + expected_advance,
        "valid record count did not advance exactly as expected",
    )
    before_highest = before["highest_nonce"]
    expected_highest = (
        expected_advance - 1
        if before_highest is None
        else before_highest + expected_advance
    )
    require(
        after["highest_nonce"] == expected_highest,
        "highest DevNonce did not advance exactly as expected",
    )
    expected_data: bytes | None = None
    if before["invalid_record_count"] == 0:
        try:
            expected_data = simulate_advances(before_data, expected_advance)
        except ValueError as error:
            failures.append(str(error))
    require(
        expected_data is not None and after_data == expected_data,
        "journal bytes do not match the exact firmware transition",
    )
    return {
        "expected_advance": expected_advance,
        "passed": not failures,
        "failures": failures,
        "changed_slots": changed_slots,
        "exact_firmware_transition": (
            expected_data is not None and after_data == expected_data
        ),
        "before": before,
        "after": after,
    }


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".partial",
        delete=False,
    ) as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    try:
        os.link(temporary, path)
    except FileExistsError as error:
        raise SystemExit(
            f"refusing to overwrite DevNonce comparison evidence: {path}"
        ) from error
    finally:
        temporary.unlink(missing_ok=True)


def require_manifest_record(journal: Path, manifest_path: Path) -> None:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"invalid journal evidence manifest: {manifest_path}") from error
    is_capture = manifest.get("passed") is True
    is_flash = manifest.get("reserved_devnonce_pages_preserved") is True
    if not is_capture and not is_flash:
        raise SystemExit(
            f"journal evidence manifest is not passing: {manifest_path}"
        )
    target = manifest.get("target", {})
    if target.get("jlink_serial") != EXPECTED_JLINK_SERIAL:
        raise SystemExit(
            f"journal evidence used an unexpected J-Link: {manifest_path}"
        )
    if is_flash:
        if (
            manifest.get("candidate", {}).get("bin_sha256")
            != EXPECTED_BIN_SHA256
        ):
            raise SystemExit(
                f"flash manifest does not identify the frozen candidate: "
                f"{manifest_path}"
            )
    else:
        for name in (
            "candidate_verification_sha256",
            "flash_manifest_sha256",
        ):
            value = manifest.get(name)
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
            ):
                raise SystemExit(
                    f"capture manifest lacks candidate/flash binding: "
                    f"{manifest_path}"
                )

    records: list[dict] = []

    def visit(value: object) -> None:
        if isinstance(value, dict):
            if {"path", "bytes", "sha256"} <= set(value):
                records.append(value)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(manifest)
    requested = journal.resolve()
    for value in records:
        try:
            recorded = verify_file_record(value)
        except SystemExit:
            continue
        if recorded.resolve() == requested:
            return
    raise SystemExit(
        f"manifest does not bind the requested journal image: {journal}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--journal", type=Path)
    parser.add_argument("--before", type=Path)
    parser.add_argument("--before-manifest", type=Path)
    parser.add_argument("--after", type=Path)
    parser.add_argument("--after-manifest", type=Path)
    parser.add_argument("--expect-advance", type=int, default=1)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output and args.output.exists():
        raise SystemExit(
            f"refusing to overwrite DevNonce comparison evidence: {args.output}"
        )
    if args.journal:
        if (
            args.before
            or args.before_manifest
            or args.after
            or args.after_manifest
        ):
            parser.error(
                "--journal cannot be combined with transition inputs"
            )
        result = decode(args.journal)
        passed = (
            result["invalid_record_count"] == 0
            and result["monotonic_unique_sequence"]
        )
        result["passed"] = passed
        result["provenance"] = {
            "journal": provenance_record(args.journal),
            "decoder": provenance_record(Path(__file__)),
        }
    else:
        if (
            args.before is None
            or args.before_manifest is None
            or args.after is None
            or args.after_manifest is None
        ):
            parser.error(
                "provide --journal or before/after images and both manifests"
            )
        if args.expect_advance < 0 or args.expect_advance > 16:
            parser.error("--expect-advance must be between 0 and 16")
        require_manifest_record(args.before, args.before_manifest)
        require_manifest_record(args.after, args.after_manifest)
        result = compare(args.before, args.after, args.expect_advance)
        passed = result["passed"]
        result["provenance"] = {
            "before": provenance_record(args.before),
            "before_manifest": provenance_record(args.before_manifest),
            "after": provenance_record(args.after),
            "after_manifest": provenance_record(args.after_manifest),
            "decoder": provenance_record(Path(__file__)),
        }
    if args.output:
        atomic_json(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
