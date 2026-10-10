#!/usr/bin/env python3
"""Install the approved formatter only on Board1 EU/AS/AU, check-only by default.

Private prior AS fields and request progress are retained before each narrow
write. Ambiguous writes stop; resume accepts only exact successful readback,
never resends an uncertain request. No US, app-level, header or hardware writes.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request

from merge_board1_regional_header import Stop, checkpoint_values, private_bytes
from provision_board1_ttn_regions import (
    Client as RegistryClient, DEFAULT_STATE, Store, TARGETS, body_for, endpoint,
    mismatches, verify_remote,
)
from ttn_inventory import ROOT, load_values

SOURCE = ROOT / "web/public/assets/docs/ttn-uplink-formatter.js"
APPROVED_SHA = "6d5fe1a071041c70dc06fbca82bffe8435fd6ee7dea40476547d4bb81325dc52"
PRIVATE_STATE = DEFAULT_STATE.with_name("regional-formatter-state.json")
SCHEMA = "stratolink.board1_regional_formatter.private.v1"
FIELDS = ("ids", "formatters", "skip_payload_crypto_override", "version_ids")
WRITE_PATHS = ["formatters.up_formatter", "formatters.up_formatter_parameter"]


class Client(RegistryClient):
    def read_as(self, target):
        host, path = endpoint(target, "as")
        request = Request(f"https://{host}/api/v3{path}?field_mask={','.join(FIELDS)}",
                          headers={"Authorization": f"Bearer {self.keys[target['key_name']]}"})
        try:
            with self.opener.open(request, timeout=20) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, {}
        except (URLError, TimeoutError, OSError, ValueError):
            return 0, {}

    def read_js(self, target):
        return self.request(target, "js")

    def put_as(self, target, body):
        if body.get("field_mask", {}).get("paths") != WRITE_PATHS or \
                set(body.get("end_device", {})) != {"ids", "formatters"} or \
                set(body["end_device"]["formatters"]) != {"up_formatter", "up_formatter_parameter"}:
            raise Stop("formatter update must contain only the two approved fields")
        return self.request(target, "as", "PUT", body)


def selected(remote):
    return {name: deepcopy(remote[name]) for name in FIELDS if name in remote}


def expected_after(before, source):
    expected = deepcopy(before)
    expected.setdefault("formatters", {}).update(
        up_formatter="FORMATTER_JAVASCRIPT", up_formatter_parameter=source)
    return expected


def load_state(store):
    if not store.path.exists() and not store.path.is_symlink():
        return {"schema": SCHEMA, "targets": list(TARGETS), "formatter_sha256": APPROVED_SHA,
                "regions": {}}
    state = json.loads(private_bytes(store.path))
    if state.get("schema") != SCHEMA or state.get("targets") != list(TARGETS) or \
            state.get("formatter_sha256") != APPROVED_SHA:
        raise Stop("private formatter checkpoint mismatch")
    if not isinstance(state.get("regions"), dict) or set(state["regions"]) != {t["region"] for t in TARGETS}:
        raise Stop("private formatter checkpoint regions mismatch")
    for row in state["regions"].values():
        if row.get("phase") not in ("prepared", "pending", "verified") or not isinstance(row.get("before"), dict):
            raise Stop("private formatter checkpoint phase/snapshot invalid")
    return state


def execute(client, store, identities, source, apply=False):
    report = {"passed": False, "mode": "apply" if apply else "check_only",
              "formatter_sha256": APPROVED_SHA, "private_checkpoint": str(store.path),
              "regions": [], "us_header_hardware_unchanged": True}
    try:
        if hashlib.sha256(source.encode()).hexdigest() != APPROVED_SHA:
            raise Stop("formatter source hash differs from reviewed repository source")
        state = load_state(store)
        initial = not state["regions"]
        observed = {}
        # Gate all three AS identities and JS root keys before any mutation.
        for target in TARGETS:
            region = target["region"]
            js_status, js = client.read_js(target)
            as_status, remote = client.read_as(target)
            if js_status != 200 or verify_remote(target, "js", identities[region], js):
                raise Stop(f"{region} fresh JS identity/root-key verification failed")
            if as_status != 200 or mismatches(
                    body_for(target, "as", identities[region])["end_device"]["ids"],
                    remote.get("ids", {}), "ids"):
                raise Stop(f"{region} fresh AS identity verification failed")
            current = selected(remote)
            observed[region] = current
            if initial:
                formatter = current.get("formatters", {})
                if not isinstance(formatter, dict) or formatter.get("up_formatter") not in (None, "FORMATTER_NONE") or \
                        formatter.get("up_formatter_parameter") not in (None, ""):
                    raise Stop(f"{region} unexpected preexisting uplink formatter")
            else:
                row = state["regions"][region]
                required = row["before"] if row["phase"] == "prepared" else expected_after(row["before"], source)
                if current != required:
                    raise Stop(f"{region} prior request cannot resume from non-exact state")
        if initial:
            state["regions"] = {region: {"phase": "prepared", "before": before}
                                for region, before in observed.items()}
        if not apply:
            report["passed"] = True
            return report
        store.save(state)
        for target in TARGETS:
            region = target["region"]
            row = state["regions"][region]
            expected = expected_after(row["before"], source)
            status, remote = client.read_as(target)
            required = row["before"] if row["phase"] == "prepared" else expected
            if status != 200 or selected(remote) != required:
                raise Stop(f"{region} AS changed before update; no write")
            if row["phase"] == "prepared":
                row["phase"] = "pending"
                store.save(state)
                body = {"end_device": {"ids": row["before"]["ids"],
                                        "formatters": {"up_formatter": "FORMATTER_JAVASCRIPT",
                                                       "up_formatter_parameter": source}},
                        "field_mask": {"paths": WRITE_PATHS}}
                status, _ = client.put_as(target, body)
                if status not in (200, 201):
                    raise Stop(f"{region} formatter write stopped with HTTP {status}; no automatic retry")
                status, remote = client.read_as(target)
                if status != 200 or selected(remote) != expected:
                    raise Stop(f"{region} formatter readback differs; checkpoint retained")
            row["phase"] = "verified"
            store.save(state)
            report["regions"].append({"region": region, "application": target["application"],
                                      "device": target["device"], "http_status": 200,
                                      "exact_formatter_readback": True, "unrelated_fields_unchanged": True})
        report["passed"] = len(report["regions"]) == 3
    except Stop as error:
        report["error"] = str(error)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        checkpoint_data = private_bytes(DEFAULT_STATE)
        checkpoint_values(checkpoint_data)
        identities = json.loads(checkpoint_data)["identities"]
        source = SOURCE.read_text()
        keys = load_values()
        if any(not keys.get(target["key_name"]) for target in TARGETS):
            raise Stop("required regional API credentials missing")
        store = Store(PRIVATE_STATE)
        if args.apply:
            with store.locked():
                result = execute(Client(keys), store, identities, source, True)
        else:
            result = execute(Client(keys), store, identities, source)
    except Stop as error:
        result = {"passed": False, "error": str(error)}
    except Exception:
        result = {"passed": False, "error": "operation stopped; private checkpoints retained; diagnostics withheld"}
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
