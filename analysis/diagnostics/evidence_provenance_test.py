#!/usr/bin/env python3
"""Regression tests for exact and append-only-prefix evidence provenance."""

from __future__ import annotations

from pathlib import Path
import tempfile

from evidence_provenance import record, verify, write_create_once


def expect_failure(value: dict, phrase: str) -> None:
    try:
        verify(value)
    except ValueError as error:
        assert phrase in str(error), error
    else:
        raise AssertionError("verification unexpectedly passed")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="stratolink-provenance-test-") as raw:
        immutable = Path(raw) / "immutable.json"
        write_create_once(immutable, b"first\n")
        assert immutable.read_bytes() == b"first\n"
        try:
            write_create_once(immutable, b"second\n")
        except FileExistsError as error:
            assert "refusing to overwrite evidence" in str(error)
        else:
            raise AssertionError("create-once evidence was overwritten")
        assert immutable.read_bytes() == b"first\n"

        path = Path(raw) / "evidence.log"
        path.write_bytes(b"alpha\n")

        exact = record(path)
        verify(exact)
        path.write_bytes(b"alpha\nbeta\n")
        expect_failure(exact, "size changed")

        path.write_bytes(b"alpha\n")
        prefix = record(path, append_allowed=True)
        path.write_bytes(b"alpha\nbeta\n")
        verify(prefix)
        path.write_bytes(b"ALPHA\nbeta\n")
        expect_failure(prefix, "prefix digest changed")

        path.write_bytes(b"a")
        expect_failure(prefix, "truncated")

        malformed = dict(prefix)
        malformed["append_allowed"] = "false"
        expect_failure(malformed, "invalid provenance record")

    print("PASS: create-once, exact, and append-only-prefix provenance")


if __name__ == "__main__":
    main()
