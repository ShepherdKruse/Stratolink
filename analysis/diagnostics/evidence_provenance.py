"""Create and verify byte-exact provenance records for qualification inputs."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile
from typing import Any


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_create_once(path: Path, payload: bytes) -> None:
    """Atomically publish immutable evidence, refusing every overwrite race."""
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    partials = sorted(path.parent.glob(f".{path.name}.*.partial"))
    collisions = ([path] if path.exists() else []) + partials
    if collisions:
        raise FileExistsError(
            "refusing to overwrite evidence: "
            + ", ".join(str(item) for item in collisions)
        )
    with tempfile.NamedTemporaryFile(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".partial",
        delete=False,
    ) as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    try:
        os.link(temporary, path)
    except FileExistsError as error:
        raise FileExistsError(
            f"refusing to overwrite evidence: {path}"
        ) from error
    finally:
        temporary.unlink(missing_ok=True)


def record(
    path: Path,
    data: bytes | None = None,
    *,
    append_allowed: bool = False,
) -> dict[str, Any]:
    raw = path.read_bytes() if data is None else data
    return {
        "path": str(path.resolve()),
        "bytes": len(raw),
        "sha256": digest(raw),
        "append_allowed": append_allowed,
    }


def verify(value: dict[str, Any]) -> None:
    try:
        path_value = value["path"]
        expected_bytes = value["bytes"]
        expected_digest = value["sha256"]
        append_allowed = value["append_allowed"]
    except (KeyError, TypeError) as error:
        raise ValueError(f"invalid provenance record: {value!r}") from error
    if (
        not isinstance(path_value, str)
        or not path_value
        or not isinstance(expected_bytes, int)
        or isinstance(expected_bytes, bool)
        or expected_bytes < 0
        or not isinstance(expected_digest, str)
        or len(expected_digest) != 64
        or any(character not in "0123456789abcdef" for character in expected_digest)
        or not isinstance(append_allowed, bool)
    ):
        raise ValueError(f"invalid provenance record: {value!r}")
    path = Path(path_value)
    if not path.is_file():
        raise ValueError(f"provenance input is missing: {path}")
    current = path.read_bytes()
    if append_allowed:
        if len(current) < expected_bytes:
            raise ValueError(f"append-only provenance input was truncated: {path}")
        observed = digest(current[:expected_bytes])
    else:
        if len(current) != expected_bytes:
            raise ValueError(f"provenance input size changed: {path}")
        observed = digest(current)
    if observed != expected_digest:
        scope = "recorded prefix" if append_allowed else "complete file"
        raise ValueError(f"provenance {scope} digest changed: {path}")


def verify_all(records: dict[str, Any]) -> None:
    if not isinstance(records, dict) or not records:
        raise ValueError("provenance record set is missing or empty")
    for name, value in records.items():
        if not isinstance(value, dict):
            raise ValueError(f"invalid provenance entry for {name}")
        verify(value)
