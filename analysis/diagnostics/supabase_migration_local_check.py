#!/usr/bin/env python3
"""Opt-in migration integration check; requires a local postgres:17.6 image.

Run: python3 analysis/diagnostics/supabase_migration_local_check.py

Uses synthetic rows and captured schema metadata only. Starts one disposable
container with no network, published ports, host mounts, or external credentials.
The PostGIS location index is excluded; API/JWT behavior is outside this check.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
import uuid


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
MIGRATIONS = ROOT / "web/lib/supabase/migrations"
CHAIN = (
    "009_wildlife_detections.sql",
    "010_b2b_packets.sql",
    "20260725090324_ttn_ingest_integrity.sql",
    "20260725184000_ctt_detection_age.sql",
    "20260725222000_telemetry_observability_v2.sql",
    "20260831043000_telemetry_server_liveness_v3.sql",
    "20261005194611_telemetry_raw_evidence.sql",
)
IMAGE = "postgres:17.6"


def identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def literal(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (dict, list)):
        value = json.dumps(value)
    return "'" + str(value).replace("'", "''") + "'"


def insert_sql(table: str, row: dict) -> str:
    return (
        f"INSERT INTO public.{identifier(table)} "
        f"({', '.join(map(identifier, row))}) VALUES "
        f"({', '.join(map(literal, row.values()))})"
    )


def fixture_sql() -> str:
    schema = json.loads((FIXTURES / "supabase_schema_20261005.json").read_text())
    security = json.loads((FIXTURES / "supabase_security_20261005.json").read_text())
    assert security["identity_or_generated_columns"] == []
    statements = [
        "CREATE ROLE anon NOLOGIN",
        "CREATE ROLE authenticated NOLOGIN",
        "CREATE ROLE service_role NOLOGIN BYPASSRLS",
        "GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role",
    ]
    # The live devices id is serial, not UUID or GENERATED IDENTITY.
    sequences = set()
    for column in schema["columns"]:
        default = column["column_default"] or ""
        match = re.fullmatch(r"nextval\('([^']+)'::regclass\)", default)
        if match:
            sequences.add(match[1])
    statements.extend(f"CREATE SEQUENCE {identifier(name)}" for name in sequences)
    for table in dict.fromkeys(c["table_name"] for c in schema["columns"]):
        columns = []
        for column in schema["columns"]:
            if column["table_name"] != table:
                continue
            definition = (
                f"{identifier(column['column_name'])} "
                f"{identifier(column['udt_schema'])}.{identifier(column['udt_name'])}"
            )
            if column["column_default"] is not None:
                definition += f" DEFAULT {column['column_default']}"
            if column["is_nullable"] == "NO":
                definition += " NOT NULL"
            columns.append(definition)
        statements.append(f"CREATE TABLE public.{identifier(table)} ({', '.join(columns)})")
    for constraint in schema["constraints"]:
        statements.append(
            f"ALTER TABLE public.{identifier(constraint['table_name'])} "
            f"ADD CONSTRAINT {identifier(constraint['conname'])} {constraint['definition']}"
        )
    constraint_names = {c["conname"] for c in schema["constraints"]}
    for index in security["indexes"]:
        if index["indexname"] not in constraint_names | {"idx_telemetry_location"}:
            statements.append(index["indexdef"])
    for view in schema["views"]:
        statements.append(f"CREATE VIEW public.{identifier(view['viewname'])} AS {view['definition']}")
    for relation in security["relations"]:
        name = identifier(relation["relname"])
        if relation["relrowsecurity"]:
            statements.append(f"ALTER TABLE public.{name} ENABLE ROW LEVEL SECURITY")
        if relation["reloptions"]:
            statements.append(f"ALTER VIEW public.{name} SET ({', '.join(relation['reloptions'])})")
    for policy in schema["policies"]:
        statement = (
            f"CREATE POLICY {identifier(policy['policyname'])} "
            f"ON public.{identifier(policy['tablename'])} FOR {policy['cmd']} "
            f"TO {', '.join(map(identifier, policy['roles']))}"
        )
        if policy["qual"] is not None:
            statement += f" USING ({policy['qual']})"
        if policy["with_check"] is not None:
            statement += f" WITH CHECK ({policy['with_check']})"
        statements.append(statement)
    for grant in security["grants"]:
        statements.append(
            f"GRANT {grant['privilege_type']} ON public.{identifier(grant['table_name'])} "
            f"TO {identifier(grant['grantee'])}"
        )
    # information_schema.column_privileges includes table-derived grants.
    # Only explicit attacl entries would need separate column GRANT statements.
    assert security["explicit_column_acls"] is None
    sequence_privileges = {"r": "SELECT", "w": "UPDATE", "U": "USAGE"}
    assert sequences == {sequence["relname"] for sequence in security["sequences"]}
    for sequence in security["sequences"]:
        for entry in sequence["acl"].strip("{}").split(","):
            grantee, acl = entry.split("=")
            privileges = ", ".join(sequence_privileges[value] for value in acl.split("/")[0])
            statements.append(f"GRANT {privileges} ON SEQUENCE {identifier(sequence['relname'])} "
                              f"TO {identifier(grantee)}")
    statements.append(security["trigger_function"])
    statements.extend(security["triggers"])
    return ";\n".join(statements) + ";\n"


class LocalPostgres:
    def __init__(self) -> None:
        self.name = f"stratolink-migration-check-{uuid.uuid4().hex[:12]}"
        self.started = False

    def docker(self, *args: str, sql: str | None = None, timeout: int = 30):
        return subprocess.run(
            ["docker", *args], input=sql, text=True, capture_output=True,
            timeout=timeout, check=False,
        )

    def __enter__(self):
        result = self.docker(
            "run", "--detach", "--rm", "--pull=never", "--network=none",
            "--name", self.name, "--memory=512m", "--cpus=1",
            "--tmpfs", "/var/lib/postgresql/data:rw,size=256m",
            "--env", "POSTGRES_HOST_AUTH_METHOD=trust", IMAGE,
            "-c", "listen_addresses=", "-c", "fsync=off",
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip())
        self.started = True
        try:
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                logs = self.docker("logs", self.name)
                ready = self.docker("exec", self.name, "pg_isready", "-U", "postgres")
                if "PostgreSQL init process complete" in logs.stdout and ready.returncode == 0:
                    return self
                time.sleep(0.25)
            raise RuntimeError("Disposable Postgres did not become ready within 60 seconds")
        except BaseException:
            self.__exit__()
            raise

    def __exit__(self, *_args):
        if self.started:
            result = self.docker("rm", "--force", self.name)
            if result.returncode:
                raise RuntimeError(f"Could not remove disposable container: {result.stderr}")
            self.started = False

    def sql(self, statement: str, *, role: str = "postgres", error: str | None = None,
            constraint: str | None = None) -> str:
        result = self.docker(
            "exec", "-i", self.name, "psql", "-X", "-qAt", "-U", "postgres",
            "--set", "ON_ERROR_STOP=1", "--set", "VERBOSITY=verbose",
            sql=f"SET statement_timeout='10s'; SET ROLE {identifier(role)};\n{statement};\n",
        )
        if error is not None:
            assert result.returncode != 0, f"Expected SQLSTATE {error}, query succeeded: {statement}"
            assert f"ERROR:  {error}:" in result.stderr, result.stderr
            if constraint is not None:
                assert f'"{constraint}"' in result.stderr, result.stderr
        elif result.returncode:
            raise AssertionError(result.stderr.strip())
        return result.stdout.strip()


def run_checks(db: LocalPostgres) -> list[str]:
    checks = []

    def passed(name: str) -> None:
        checks.append(name)
        print(f"PASS {name}", flush=True)

    db.sql(fixture_sql())
    assert db.sql("SHOW server_version_num") == "170006"
    device = {
        "device_id": "stratolink-1-fixture", "claim_code": "synthetic-claim",
        "launch_token_hash": "synthetic-hash", "status": "flying",
    }
    assert db.sql(insert_sql("devices", device) + " RETURNING id", role="service_role") == "1"
    passed("captured schema reconstructed; service role serial device insert")

    # Synthetic Board-1-shaped old-formatter drift: raw wire-v3, decoded as v2.
    raw = bytearray(40)
    raw[18:20] = bytes.fromhex("1234")
    raw[35] = 7
    raw[36:38] = bytes.fromhex("91ff")
    payload = base64.b64encode(raw).decode("ascii")
    legacy = {
        "device_id": device["device_id"], "time": "2026-10-05T19:00:00Z",
        "telemetry_version": 2, "gps_fix_age_min": 37375,
        "power_tier": None, "reset_cause": None, "boot_count": 7,
        "lat": 0, "lon": 0, "altitude_m": 0, "gps_satellites": 0,
        "gps_speed": 0, "gps_heading": 0, "velocity_x": 0, "velocity_y": 0,
        "f_port": 1, "frm_payload": payload,
    }
    legacy_id = db.sql(insert_sql("telemetry", legacy) + " RETURNING id", role="service_role")
    legacy_before = db.sql(f"SELECT row_to_json(t) FROM telemetry t WHERE id={literal(legacy_id)}")
    wildlife = {
        "device_id": device["device_id"], "time": "2026-10-05T19:00:00Z",
        "raw_tag_id": 4294967295, "motus_tag_id": None, "motus_valid": False,
        "detection_rssi": -90, "hits": 1, "listen_window": 65535,
    }
    for index, filename in enumerate(CHAIN):
        db.sql((MIGRATIONS / filename).read_text())
        db.sql(insert_sql("telemetry", {**legacy, "time": f"2026-10-05T19:01:0{index}Z"}), role="service_role")
        if filename.startswith("009_"):
            db.sql(insert_sql("wildlife_detections", wildlife), role="service_role")
        if filename.startswith("20260725222000_"):
            v2_status = {
                "device_id": device["device_id"], "ttn_device_id": "synthetic-v2-us",
                "telemetry_version": None, "power_tier": 0, "reset_cause": 0,
                "boot_count": 7, "relay_enabled": False, "relay_fwd_delta": 0, "ctt_tags_delta": 0,
            }
            db.sql(insert_sql("telemetry", v2_status), role="service_role", error="23514",
                   constraint="telemetry_observability_version_fields_check")
            db.sql(insert_sql("telemetry", {**v2_status, "telemetry_version": 2}), role="service_role")
            passed("v2 stage rejects NULL version with status; complete v2 accepted")
        passed(f"migration {filename}; legacy route insert remains accepted")
    after = json.loads(db.sql(f"SELECT row_to_json(t) FROM telemetry t WHERE id={literal(legacy_id)}"))
    assert {key: after[key] for key in json.loads(legacy_before)} == json.loads(legacy_before)
    assert db.sql("SELECT event_version FROM wildlife_detections") == "1"
    passed("historical drift values preserved; existing CTT v1 row backfilled")

    identity = {
        "ttn_device_id": "stratolink-1-fixture-us", "dev_addr": "260CACD0",
        "ttn_received_at": "2026-10-05T19:02:00.123456Z", "f_cnt": 7,
        "session_key_id": None,
    }
    gateways = [{"gateway_id": "synthetic-gateway", "rssi": -87, "snr": 5.5,
                 "lat": None, "lon": None, "alt": None}]
    metadata = [{"gateway_ids": {"gateway_id": "synthetic-gateway"}, "rssi": -87,
                 "snr": 5.5, "channel_rssi": -88, "received_at": "2026-10-05T19:02:00.1Z"}]
    strict = {
        "device_id": device["device_id"], "time": identity["ttn_received_at"],
        **identity, "telemetry_version": 3, "power_tier": 0, "reset_cause": 0,
        "boot_count": 7, "gps_fix_age_min": None, "command_ack_seq": None,
        "relay_enabled": False, "relay_fwd_delta": 0, "ctt_tags_delta": 0,
        "server_proof_count_mod8": 1, "server_qualified_miss_streak": 2,
        "server_recovery_parity": 1, "gps_satellites": 0,
        "frm_payload": payload, "f_port": 1, "gateways": gateways, "rx_metadata": metadata,
    }
    strict_id = db.sql(insert_sql("telemetry", strict) + " RETURNING id", role="service_role")
    stored = json.loads(db.sql(
        f"SELECT json_build_object('frm_payload',frm_payload,'f_port',f_port,"
        f"'gateways',gateways,'rx_metadata',rx_metadata) FROM telemetry WHERE id={literal(strict_id)}"
    ))
    assert stored == {key: strict[key] for key in stored}
    assert base64.b64decode(stored["frm_payload"]) == raw
    passed("strict identity-bearing v3 NOGPS insert; raw bytes and gateway JSON roundtrip")
    fixed = {**strict, "f_cnt": 8, "lat": 37.5, "lon": -122.5, "altitude_m": 100,
             "gps_satellites": 8, "gps_speed": 2, "gps_heading": 45,
             "velocity_x": 1, "velocity_y": 1, "gps_fix_age_min": 510}
    db.sql(insert_sql("telemetry", fixed), role="service_role")
    passed("strict v3 valid GPS fix with maximum 510-minute age accepted")

    for version in (None, 1):
        db.sql(insert_sql("telemetry", {
            "device_id": device["device_id"], "ttn_device_id": "synthetic-legacy-us",
            "telemetry_version": version,
        }), role="service_role")
    passed("identity-bearing legacy NULL/v1 rows with no later status fields remain accepted")

    for changes, constraint in (
        ({"server_proof_count_mod8": None}, "telemetry_observability_version_fields_check"),
        ({"power_tier": None}, "telemetry_observability_version_fields_check"),
        ({"gps_fix_age_min": 511}, "telemetry_observability_version_fields_check"),
        ({"server_proof_count_mod8": 8}, "telemetry_server_proof_range"),
        ({"reset_cause": 7}, "telemetry_reset_cause_range"),
        ({"lat": 37.5}, "telemetry_gps_state_check"),
        ({"telemetry_version": None}, "telemetry_observability_version_fields_check"),
    ):
        db.sql(insert_sql("telemetry", {**strict, "f_cnt": 100, **changes}),
               role="service_role", error="23514", constraint=constraint)
    passed("invalid v3 required/range fields and mixed GPS state rejected by named constraints")

    v1 = {**wildlife, **identity, "event_version": 1, "f_cnt": 8}
    v2 = {**wildlife, **identity, "event_version": 2, "listen_window": None,
          "detection_age_min": 60, "detected_at": "2026-10-05T18:02:00.123456Z"}
    db.sql(insert_sql("wildlife_detections", v1), role="service_role")
    db.sql(insert_sql("wildlife_detections", v2), role="service_role")
    db.sql(insert_sql("wildlife_detections", {**v2, "f_cnt": 100, "listen_window": 1}),
           role="service_role", error="23514", constraint="wildlife_detections_version_fields_check")
    passed("service-role CTT v1/v2 accepted; mixed version fields rejected")

    b2b = {
        **identity, "gateway_balloon_id": device["device_id"], "time": identity["ttn_received_at"],
        "source_balloon_id": 2, "message_id": 7, "ttl": 1, "frame_type": "crumb",
        "payload_base64": "AQID", "raw_frame_base64": "AQIDBA==", "crumbs": [],
    }
    db.sql(insert_sql("b2b_packets", b2b), role="service_role")
    passed("service-role B2B insert accepted without public RLS policy")
    for table, row in (("telemetry", strict), ("wildlife_detections", v2), ("b2b_packets", b2b)):
        db.sql(insert_sql(table, row), role="service_role", error="23505",
               constraint=f"idx_{table}_ttn_delivery")
        db.sql(insert_sql(table, {**row, "ttn_received_at": "2026-10-05T19:03:00Z"}), role="service_role")
    passed("three TTN unique delivery indexes reject exact retries; later FCnt reuse accepted")

    for role in ("anon", "authenticated"):
        for table in ("telemetry", "wildlife_detections", "latest_telemetry"):
            assert int(db.sql(f"SELECT count(*) FROM public.{table}", role=role)) > 0
        assert db.sql("SELECT device_id FROM devices", role=role) == device["device_id"]
        for column in ("claim_code", "launch_token_hash", "launch_token_expires_at"):
            db.sql(f"SELECT {column} FROM devices", role=role, error="42501")
        db.sql("SELECT * FROM b2b_packets", role=role, error="42501")
        for table, row in (("telemetry", strict), ("wildlife_detections", v2),
                           ("b2b_packets", b2b), ("devices", device)):
            db.sql(insert_sql(table, row), role=role, error="42501")
            db.sql(f"UPDATE {table} SET time=now()" if table != "devices"
                   else "UPDATE devices SET status='storage'", role=role, error="42501")
            db.sql(f"DELETE FROM {table}", role=role, error="42501")
            db.sql(f"TRUNCATE {table}", role=role, error="42501")
        passed(f"{role} public reads accepted; table writes, device secrets, and B2B reads denied")

    # A restrictive policy must affect the view as well as the underlying table.
    assert db.sql("BEGIN; CREATE POLICY fixture_hide_rows ON telemetry AS RESTRICTIVE "
                  "FOR SELECT TO anon USING (false); SET LOCAL ROLE anon; "
                  "SELECT count(*) FROM latest_telemetry; ROLLBACK") == "0", "view bypassed caller RLS"
    passed("latest_telemetry honors caller RLS through security_invoker")

    counts_before = db.sql("SELECT (SELECT count(*) FROM telemetry), "
                           "(SELECT count(*) FROM wildlife_detections), (SELECT count(*) FROM b2b_packets)")
    for filename in CHAIN:
        db.sql((MIGRATIONS / filename).read_text())
    counts_after = db.sql("SELECT (SELECT count(*) FROM telemetry), "
                          "(SELECT count(*) FROM wildlife_detections), (SELECT count(*) FROM b2b_packets)")
    assert counts_after == counts_before
    db.sql(insert_sql("telemetry", {**strict, "f_cnt": 200}), role="service_role")
    db.sql(insert_sql("telemetry", legacy), role="service_role")
    passed("complete migration rerun preserves row counts and strict/legacy insert compatibility")
    return checks


def main() -> None:
    with LocalPostgres() as db:
        checks = run_checks(db)
    print(json.dumps({
        "result": "pass", "checks": len(checks), "image": IMAGE,
        "isolation": "network none; no ports; no host mounts; temporary data; container removed",
        "migration_sha256": {name: hashlib.sha256((MIGRATIONS / name).read_bytes()).hexdigest()
                             for name in CHAIN},
        "scope_limits": [
            "Synthetic data only; no production row export or external connections.",
            "PostGIS idx_telemetry_location omitted; other captured indexes modeled.",
            "Does not exercise Supabase PostgREST/JWT, webhook HTTP, TTN, or deployment concurrency.",
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
