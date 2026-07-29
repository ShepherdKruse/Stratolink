#!/usr/bin/env python3
"""Regression checks for the read-only Supabase contract probe."""

from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import supabase_schema_probe as probe


class FakeResponse:
    status = 200

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None


def main() -> None:
    requests = []

    def fake_urlopen(request, **_kwargs):
        requests.append(request)
        return FakeResponse()

    with tempfile.TemporaryDirectory() as directory:
        env_file = Path(directory) / "env"
        public_key = "fixture-publishable-value"
        forbidden_secret = "fixture-service-role-value"
        env_file.write_text(
            "SUPABASE_URL=https://example.supabase.co\n"
            f"SUPABASE_PUBLISHABLE_KEY={public_key}\n"
            f"SUPABASE_SERVICE_ROLE_KEY={forbidden_secret}\n"
            "SBKEY=legacy-secret-value\n",
            encoding="utf-8",
        )
        output = io.StringIO()
        with (
            patch.object(probe, "ENV_FILE", env_file),
            patch.object(probe, "urlopen", fake_urlopen),
            redirect_stdout(output),
        ):
            probe.main()

    rendered = output.getvalue()
    assert public_key not in rendered
    assert forbidden_secret not in rendered
    assert "legacy-secret-value" not in rendered
    report = json.loads(rendered)
    assert report["contract_ready"] is True
    assert len(report["probes"]) == len(probe.PROBES) == len(requests)

    for request, (table, expected_columns) in zip(
        requests, probe.PROBES.items(), strict=True
    ):
        parsed = urlparse(request.full_url)
        assert parsed.path == f"/rest/v1/{table}"
        query = parse_qs(parsed.query)
        assert query["limit"] == ["0"]
        assert query["select"] == [",".join(expected_columns)]
        assert request.headers["Apikey"] == public_key
        assert request.headers["Authorization"] == f"Bearer {public_key}"

    telemetry = probe.PROBES["telemetry"]
    for column in (
        "ttn_device_id",
        "f_cnt",
        "telemetry_version",
        "gps_fix_age_min",
        "command_ack_seq",
        "relay_fwd_delta",
        "ctt_tags_delta",
    ):
        assert column in telemetry
    wildlife = probe.PROBES["wildlife_detections"]
    assert wildlife[-3:] == ("event_version", "detection_age_min", "detected_at")

    print("PASS: Supabase probe pins the full read-only backend contract")


if __name__ == "__main__":
    main()
