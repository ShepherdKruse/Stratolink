#!/usr/bin/env python3
"""The cached Supabase evidence export must be create-once."""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
import json
import subprocess
import sys
import tempfile


HERE = Path(__file__).resolve().parent
TOOL = HERE / "export_supabase_soak.py"

from export_supabase_soak import through_ttn_time, write_create_once


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="stratolink-supabase-export-") as raw:
        directory = Path(raw)
        ttn = directory / "ttn.jsonl"
        ttn.write_text(
            json.dumps(
                {
                    "event": "ttn_uplink",
                    "device_id": "stratolink-2",
                    "received_at": "2026-07-25T20:23:39.193482+00:00",
                }
            ) + "\n",
            encoding="utf-8",
        )
        bound = datetime.fromisoformat(through_ttn_time(ttn))
        assert bound == datetime.fromisoformat(
            "2026-07-25T20:23:44.193482+00:00"
        )

        output = directory / "evidence.json"
        output.write_text("preserved\n", encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, str(TOOL), "--output", str(output)],
            text=True,
            capture_output=True,
        )
        assert completed.returncode != 0
        assert "refusing to overwrite" in completed.stderr
        assert output.read_text(encoding="utf-8") == "preserved\n"

        fresh = directory / "fresh.json"
        write_create_once(fresh, [{"device_id": "stratolink-2"}])
        preserved = fresh.read_bytes()
        try:
            write_create_once(fresh, [{"device_id": "wrong"}])
        except SystemExit as error:
            assert "refusing to overwrite" in str(error)
        else:
            raise AssertionError("create-once export overwrote existing evidence")
        assert fresh.read_bytes() == preserved

    print("PASS: Supabase evidence export is atomically create-once")


if __name__ == "__main__":
    main()
