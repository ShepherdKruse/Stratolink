#!/usr/bin/env python3
"""Collector lifecycle regressions: Paho v2 codes and create-once logs."""

from pathlib import Path
import tempfile

from ttn_soak_monitor import (
    mqtt_reason_code_value,
    open_create_once_log,
    protobuf_uint32,
)


class PahoV2Reason:
    value = 128

    def __int__(self) -> int:
        raise TypeError("Paho ReasonCode is not directly int-convertible")

    def __str__(self) -> str:
        return "Unspecified error"


class OpaqueReason:
    def __str__(self) -> str:
        return "opaque-disconnect"


def main() -> None:
    assert mqtt_reason_code_value(0) == 0
    assert mqtt_reason_code_value(PahoV2Reason()) == 128
    assert mqtt_reason_code_value(OpaqueReason()) == "opaque-disconnect"
    assert protobuf_uint32({}, "f_cnt") == 0
    assert protobuf_uint32({"f_cnt": 1}, "f_cnt") == 1
    assert protobuf_uint32({"f_cnt": None}, "f_cnt") is None
    assert protobuf_uint32({"f_cnt": True}, "f_cnt") is None
    assert protobuf_uint32({"f_cnt": -1}, "f_cnt") is None
    assert protobuf_uint32({"f_cnt": 0x100000000}, "f_cnt") is None

    with tempfile.TemporaryDirectory(prefix="stratolink-ttn-create-once-") as raw:
        path = Path(raw) / "nested" / "soak.jsonl"
        with open_create_once_log(path) as handle:
            handle.write("first\n")
        preserved = path.read_bytes()
        try:
            open_create_once_log(path)
        except SystemExit as error:
            assert "refusing to append to existing TTN evidence" in str(error)
        else:
            raise AssertionError("collector reopened existing evidence")
        assert path.read_bytes() == preserved

    print("PASS: TTN collector handles Paho v2 disconnects and is create-once")


if __name__ == "__main__":
    main()
