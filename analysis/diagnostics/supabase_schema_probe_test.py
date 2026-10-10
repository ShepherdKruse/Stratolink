#!/usr/bin/env python3
"""Regression checks for the read-only Supabase contract probe."""

from __future__ import annotations

import base64
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
from urllib.error import HTTPError
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
        if urlparse(request.full_url).path == "/rest/v1/b2b_packets":
            raise HTTPError(
                request.full_url,
                403,
                "permission denied",
                {},
                io.BytesIO(b'{"code":"42501","message":"permission denied"}'),
            )
        return FakeResponse()

    with tempfile.TemporaryDirectory() as directory:
        env_file = Path(directory) / "env"
        public_key = "sb_publishable_fixture_value"
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

        exposed_output = io.StringIO()
        with (
            patch.object(probe, "ENV_FILE", env_file),
            patch.object(probe, "urlopen", lambda *_args, **_kwargs: FakeResponse()),
            redirect_stdout(exposed_output),
        ):
            probe.main()

        def missing_private_urlopen(request, **_kwargs):
            if urlparse(request.full_url).path == "/rest/v1/b2b_packets":
                raise HTTPError(
                    request.full_url,
                    404,
                    "not found",
                    {},
                    io.BytesIO(
                        b'{"code":"PGRST205","message":"table missing"}'
                    ),
                )
            return FakeResponse()

        missing_output = io.StringIO()
        with (
            patch.object(probe, "ENV_FILE", env_file),
            patch.object(probe, "urlopen", missing_private_urlopen),
            redirect_stdout(missing_output),
        ):
            probe.main()

        # A schema missing any raw-evidence column cannot accept the current
        # webhook insert, even when the decoded fields and private table exist.
        additional_requests_start = len(requests)
        for missing_column in ("frm_payload", "f_port", "gateways", "rx_metadata"):
            def missing_raw_urlopen(request, **kwargs):
                parsed = urlparse(request.full_url)
                selected = parse_qs(parsed.query).get("select", [""])[0].split(",")
                if parsed.path == "/rest/v1/telemetry" and missing_column in selected:
                    raise HTTPError(
                        request.full_url, 400, "column missing", {},
                        io.BytesIO(json.dumps({
                            "code": "42703", "message": f"column {missing_column} does not exist",
                        }).encode("utf-8")),
                    )
                return fake_urlopen(request, **kwargs)

            missing_raw_output = io.StringIO()
            with (
                patch.object(probe, "ENV_FILE", env_file),
                patch.object(probe, "urlopen", missing_raw_urlopen),
                redirect_stdout(missing_raw_output),
            ):
                probe.main()
            missing_raw_report = json.loads(missing_raw_output.getvalue())
            assert missing_raw_report["contract_ready"] is False, missing_column
            assert missing_raw_report["probes"][0]["code"] == "42703"
        del requests[additional_requests_start:]

    rendered = output.getvalue()
    assert public_key not in rendered
    assert forbidden_secret not in rendered
    assert "legacy-secret-value" not in rendered
    report = json.loads(rendered)
    assert report["contract_ready"] is True
    assert report["public_contract_ready"] is True
    assert report["private_boundary_ready"] is True
    assert report["admin_verification_required"] == ["b2b_packets"]
    expected_probe_count = len(probe.PUBLIC_PROBES) + len(
        probe.PRIVATE_DENIAL_PROBES
    )
    assert len(report["probes"]) == expected_probe_count == len(requests)

    for request, (table, expected_columns) in zip(
        requests[: len(probe.PUBLIC_PROBES)],
        probe.PUBLIC_PROBES.items(),
        strict=True,
    ):
        parsed = urlparse(request.full_url)
        assert parsed.path == f"/rest/v1/{table}"
        query = parse_qs(parsed.query)
        assert query["limit"] == ["0"]
        assert query["select"] == [",".join(expected_columns)]
        assert request.headers["Apikey"] == public_key
        assert request.headers["Authorization"] == f"Bearer {public_key}"

    private_request = requests[-1]
    private_parsed = urlparse(private_request.full_url)
    assert private_parsed.path == "/rest/v1/b2b_packets"
    private_query = parse_qs(private_parsed.query)
    assert private_query["select"] == ["id"]
    private_result = report["probes"][-1]
    assert private_result["expected_access"] == "service_role_only"
    assert private_result["public_access_denied"] is True
    assert private_result["private_table_existence_verified"] is True
    assert private_result["private_columns_verified"] is False

    exposed_report = json.loads(exposed_output.getvalue())
    assert exposed_report["contract_ready"] is False
    assert exposed_report["private_boundary_ready"] is False
    assert exposed_report["probes"][-1]["public_access_denied"] is False

    missing_report = json.loads(missing_output.getvalue())
    assert missing_report["contract_ready"] is False
    assert missing_report["private_boundary_ready"] is False
    assert missing_report["probes"][-1]["code"] == "PGRST205"
    assert missing_report["probes"][-1]["public_access_denied"] is False
    assert missing_report["probes"][-1]["private_table_existence_verified"] is False

    def fixture_jwt(role: str) -> str:
        encoded = base64.urlsafe_b64encode(
            json.dumps({"role": role}).encode("utf-8")
        ).decode("ascii").rstrip("=")
        return f"header.{encoded}.signature"

    assert probe.is_publishable_key(public_key)
    assert probe.is_publishable_key(fixture_jwt("anon"))
    assert not probe.is_publishable_key("fixture-publishable-value")
    # Construct the secret-key prefix at runtime so this negative fixture does
    # not itself look like a live credential to the repository boundary scan.
    assert not probe.is_publishable_key("sb_" + "secret_" + "fixture_value")
    assert not probe.is_publishable_key(fixture_jwt("service_role"))

    telemetry = probe.PUBLIC_PROBES["telemetry"]
    for column in (
        "ttn_device_id",
        "f_cnt",
        "telemetry_version",
        "gps_fix_age_min",
        "server_proof_count_mod8",
        "server_qualified_miss_streak",
        "server_recovery_parity",
        "command_ack_seq",
        "relay_fwd_delta",
        "ctt_tags_delta",
    ):
        assert column in telemetry
    wildlife = probe.PUBLIC_PROBES["wildlife_detections"]
    assert wildlife[-3:] == ("event_version", "detection_age_min", "detected_at")

    print("PASS: Supabase probe pins public reads and private B2B denial")


if __name__ == "__main__":
    main()
