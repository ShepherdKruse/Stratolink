#!/usr/bin/env python3
"""Parser and immutable-output regression for static_stack_usage_audit.py."""

from pathlib import Path

from static_stack_usage_audit import function_is_linked, parse_su_line


SOURCE = Path(__file__).with_name("static_stack_usage_audit.py")


def main() -> int:
    assert "write_create_once(args.output" in SOURCE.read_text(encoding="utf-8")
    row = parse_su_line("src/main.cpp:261:6:void loop()\t272\tstatic")
    assert row == {
        "source": "src/main.cpp",
        "line": 261,
        "column": 6,
        "function": "void loop()",
        "bytes": 272,
        "qualifier": "static",
    }
    assert parse_su_line("malformed") is None
    names = {"loop()", "Thing::run(unsigned long)"}
    assert function_is_linked("void loop()", names)
    assert function_is_linked("bool Thing::run(unsigned long)", names)
    assert not function_is_linked("void unused()", names)
    print("PASS: static-stack usage parser and linked-name matching")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
