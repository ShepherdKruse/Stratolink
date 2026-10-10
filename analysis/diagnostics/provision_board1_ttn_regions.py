#!/usr/bin/env python3
"""Guarded registration of only Board1's missing EU/AS/AU TTN identities.

Check-only by default. --apply requires twelve absence/exact-resume reads
before any write, checkpoints every allocation/write before sending it, and
never deletes or writes a registration observed to exist. Registry PUT requests
are unconditional: operators must exclude concurrent external registrars, since
the immediate absence recheck cannot eliminate a GET-to-PUT race. An uncertain allocation
cannot be retried; an uncertain registration can resume only after exact
readback. Private EUIs/AppKeys remain in a mode-0600 checkpoint in a mode-0700
directory. This tool never touches firmware headers, hardware, or the US device.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import secrets
import ssl
import stat
import tempfile
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

import certifi

from ttn_identity_audit import wire_bytes
from ttn_inventory import load_values


IS_HOST = "eu1.cloud.thethings.network"
JOIN_EUI = "0000000000000000"
COMPONENTS = ("is", "js", "ns", "as")
TARGETS = (
    {"region": "EU", "application": "eu-stratolink", "device": "stratolink-1-eu",
     "host": IS_HOST, "plan": "EU_863_870_TTN", "rx2_hz": 869525000,
     "rx2_dr": 3, "key_name": "TTN_EU_API_KEY"},
    {"region": "AS", "application": "as-stratolink", "device": "stratolink-1-as",
     "host": IS_HOST, "plan": "AS_920_923", "rx2_hz": 923200000,
     "rx2_dr": 2, "key_name": "TTN_AS_API_KEY"},
    {"region": "AU", "application": "stratolink", "device": "stratolink-1-au",
     "host": "nam1.cloud.thethings.network", "plan": "AU_915_928_FSB_2",
     "rx2_hz": 923300000, "rx2_dr": 8, "key_name": "TTN_NA_API_KEY"},
)
SCHEMA = "stratolink.board1_ttn_regions.private.v1"
DEFAULT_STATE = Path.home() / ".config/stratolink/board1-regional-registration/state.json"


class Stop(RuntimeError):
    """Only fixed, redacted messages may cross this boundary."""


def body_for(target: dict, component: str, identity: dict) -> dict:
    ids = {"application_ids": {"application_id": target["application"]},
           "device_id": target["device"], "dev_eui": identity["dev_eui"],
           "join_eui": JOIN_EUI}
    id_paths = ["ids.device_id", "ids.dev_eui", "ids.join_eui"]
    servers = {"network_server_address": target["host"],
               "application_server_address": target["host"]}
    if component == "is":
        return {"end_device": {"ids": ids, "name": f"StratoLink-1 {target['region']}",
                               **servers, "join_server_address": target["host"]}}
    if component == "js":
        fields = {**servers, "root_keys": {"app_key": {"key": identity["app_key"]}},
                  "resets_join_nonces": False}
        paths = list(servers) + ["root_keys.app_key.key", "resets_join_nonces"]
    elif component == "ns":
        mac = {
            "rx1_delay": 5, "desired_rx1_delay": 5,
            "rx1_data_rate_offset": 0, "desired_rx1_data_rate_offset": 0,
            "rx2_frequency": str(target["rx2_hz"]),
            "desired_rx2_frequency": str(target["rx2_hz"]),
            "rx2_data_rate_index": target["rx2_dr"],
            "desired_rx2_data_rate_index": target["rx2_dr"],
            "status_count_periodicity": 0, "status_time_periodicity": "0s",
            "use_adr": False, "schedule_downlinks": True,
            "supports_32_bit_f_cnt": True, "resets_f_cnt": False,
        }
        fields = {"supports_join": True, "supports_class_b": False,
                  "supports_class_c": False, "lorawan_version": "MAC_V1_0_3",
                  "lorawan_phy_version": "PHY_V1_0_3_REV_A",
                  "frequency_plan_id": target["plan"], "mac_settings": mac}
        paths = [name for name in fields if name != "mac_settings"]
        paths += [f"mac_settings.{name}" for name in mac]
    elif component == "as":
        fields = {"skip_payload_crypto_override": False}
        paths = list(fields)
    else:
        raise Stop("unknown registry component")
    return {"end_device": {"ids": ids, **fields},
            "field_mask": {"paths": id_paths + paths}}


def endpoint(target: dict, component: str) -> tuple[str, str]:
    if target not in TARGETS or component not in COMPONENTS:
        raise Stop("request is outside fixed Board1 regional targets")
    prefix = "" if component == "is" else f"/{component}"
    return (IS_HOST if component == "is" else target["host"],
            f"{prefix}/applications/{target['application']}/devices/{target['device']}")


def read_mask(target: dict, component: str) -> str:
    dummy = {"dev_eui": "01" * 8, "app_key": "01" * 16}
    body = body_for(target, component, dummy)
    fields = body.get("field_mask", {}).get("paths", list(body["end_device"]))
    fields = list(dict.fromkeys(["ids", *fields]))
    if component == "js":
        fields += ["used_dev_nonces", "last_dev_nonce"]
    return ",".join(fields)


def mismatches(expected: dict, actual: dict, prefix: str = "") -> list[str]:
    """Compare selected fields, normalizing only protobuf wire encodings."""
    missing = []
    scalar_false = {"supports_class_b", "supports_class_c", "resets_join_nonces"}
    for name, value in expected.items():
        path = f"{prefix}.{name}" if prefix else name
        observed = actual.get(name) if isinstance(actual, dict) else None
        if isinstance(value, dict):
            missing.extend(mismatches(value, observed, path))
        elif path in ("ids.dev_eui", "ids.join_eui", "root_keys.app_key.key"):
            size = 16 if path == "root_keys.app_key.key" else 8
            if wire_bytes(value, size) != wire_bytes(observed, size):
                missing.append(path)
        elif isinstance(value, bool):
            if observed is not value and not (name in scalar_false and not value and observed is None):
                missing.append(path)
        elif type(value) is int:
            enum_prefix = None
            if "data_rate_offset" in name:
                enum_prefix = "DATA_RATE_OFFSET_"
            elif "data_rate_index" in name:
                enum_prefix = "DATA_RATE_"
            elif "rx1_delay" in name:
                enum_prefix = "RX_DELAY_"
            if not (type(observed) is int and observed == value) and not (
                isinstance(observed, str) and observed in (
                    str(value), f"{enum_prefix}{value}" if enum_prefix else str(value))
            ):
                missing.append(path)
        elif value != observed:
            missing.append(path)
    return missing


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client:
    def __init__(self, keys: dict):
        self.keys = keys
        self.opener = build_opener(
            NoRedirect(), HTTPSHandler(context=ssl.create_default_context(cafile=certifi.where())))

    def request(self, target: dict, component: str, method: str = "GET", body=None,
                allocate: bool = False) -> tuple[int, dict]:
        host, path = endpoint(target, component)
        if allocate:
            if component != "is" or method != "POST":
                raise Stop("invalid allocation operation")
            path = f"/applications/{target['application']}/dev-eui"
        elif method == "GET":
            path += f"?field_mask={read_mask(target, component)}"
        elif component == "is" and method == "POST":
            path = path.rsplit("/", 1)[0]
        elif component == "is" or method != "PUT":
            raise Stop("existing identity updates and deletion are prohibited")
        key = self.keys.get(target["key_name"])
        if not key:
            raise Stop(f"missing API key for {target['region']}")
        data = None if method == "GET" else json.dumps(body or {}).encode()
        request = Request(f"https://{host}/api/v3{path}", data=data, method=method,
                          headers={"Authorization": f"Bearer {key}",
                                   "Content-Type": "application/json"})
        try:
            with self.opener.open(request, timeout=20) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            # Never expose a server body: it can echo submitted key material.
            return error.code, {}
        except (URLError, TimeoutError, OSError, ValueError):
            return 0, {}


class Store:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict:
        if not self.path.exists():
            return {"schema": SCHEMA, "targets": list(TARGETS), "identities": {}}
        if self.path.is_symlink() or not self.path.is_file():
            raise Stop("private checkpoint must be a regular file")
        if stat.S_IMODE(self.path.stat().st_mode) & 0o077:
            raise Stop("private checkpoint permissions must exclude group/other")
        try:
            state = json.loads(self.path.read_text())
        except (OSError, ValueError):
            raise Stop("private checkpoint is unreadable; do not replace it") from None
        if state.get("schema") != SCHEMA or state.get("targets") != list(TARGETS):
            raise Stop("private checkpoint target/schema mismatch")
        identities = state.get("identities")
        if not isinstance(identities, dict) or set(identities) - {t["region"] for t in TARGETS}:
            raise Stop("private checkpoint has unexpected identities")
        for identity in identities.values():
            if identity.get("dev_eui"):
                if not wire_bytes(identity["dev_eui"], 8) or not wire_bytes(identity.get("app_key"), 16):
                    raise Stop("private checkpoint contains incomplete credentials")
        return state

    def save(self, state: dict) -> None:
        if self.path.parent.is_symlink():
            raise Stop("private checkpoint directory must not be a symlink")
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if stat.S_IMODE(self.path.parent.stat().st_mode) != 0o700:
            raise Stop("private checkpoint directory must have mode 0700")
        state["updated_utc"] = datetime.now(timezone.utc).isoformat()
        with tempfile.NamedTemporaryFile(mode="w", dir=self.path.parent,
                                         prefix=".state-", delete=False) as handle:
            temporary = Path(handle.name)
            os.fchmod(handle.fileno(), 0o600)
            json.dump(state, handle, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.path)
        directory_fd = os.open(self.path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    @contextmanager
    def locked(self):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.path.parent.is_symlink() or stat.S_IMODE(self.path.parent.stat().st_mode) != 0o700:
            raise Stop("private checkpoint directory must be a real mode-0700 directory")
        fd = os.open(self.path.with_suffix(".lock"), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise Stop("another regional registration executor holds the checkpoint") from None
            yield
        finally:
            os.close(fd)


def verify_remote(target: dict, component: str, identity: dict, remote: dict) -> list[str]:
    failures = mismatches(body_for(target, component, identity)["end_device"], remote)
    if component == "js":
        if remote.get("used_dev_nonces") or remote.get("last_dev_nonce") is not None:
            failures.append("new_identity_nonce_history_not_empty")
    return failures


def execute(client, store: Store, apply: bool = False) -> dict:
    state = store.load()
    report = {"schema": "stratolink.board1_ttn_regions.redacted.v1", "mode": "apply" if apply else "check_only",
              "private_checkpoint": str(store.path), "passed": False, "preflight": [],
              "registrations": [], "header_changed": False, "us_device_accessed": False}
    try:
        # This entire twelve-registry gate completes before any allocation/write.
        for target in TARGETS:
            identity = state["identities"].get(target["region"], {})
            for component in COMPONENTS:
                status, remote = client.request(target, component)
                prior = identity.get("registrations", {}).get(component)
                errors = []
                if status == 200:
                    errors = (verify_remote(target, component, identity, remote)
                              if identity.get("dev_eui") and prior else ["unexpected_existing_record"])
                elif status != 404:
                    errors = ["registry_read_failed"]
                elif prior:
                    errors = ["attempted_registration_now_absent_no_automatic_retry"]
                report["preflight"].append({"region": target["region"], "component": component,
                                            "http_status": status, "mismatches": errors})
        if len(report["preflight"]) != 12 or any(r["mismatches"] for r in report["preflight"]):
            raise Stop("twelve-registry preflight refused unexpected or unreadable state")
        if not apply:
            report["passed"] = True
            return report
        for target in TARGETS:
            region = target["region"]
            identity = state["identities"].setdefault(region, {})
            if not identity.get("dev_eui"):
                if identity.get("allocation_started"):
                    raise Stop(f"{region} allocation was already attempted; manual reconciliation required")
                identity["allocation_started"] = True
                store.save(state)
                status, allocation = client.request(target, "is", "POST", allocate=True)
                if status not in (200, 201):
                    identity["allocation_http_status"] = status
                    store.save(state)
                    raise Stop(f"{region} DevEUI allocation stopped with HTTP {status}; no automatic retry")
                allocated = wire_bytes(allocation.get("dev_eui"), 8)
                if allocated is None or not any(allocated):
                    raise Stop(f"{region} allocation response was invalid; no automatic retry")
                eui = allocated.hex().upper()
                if any(other.get("dev_eui") == eui for other in state["identities"].values()):
                    raise Stop("issued DevEUI collides with retained identity")
                identity.update(dev_eui=eui, app_key=secrets.token_hex(16).upper(), registrations={})
                store.save(state)
            for component in COMPONENTS:
                status, remote = client.request(target, component)
                prior = identity["registrations"].get(component)
                if status == 200:
                    if not prior or verify_remote(target, component, identity, remote):
                        raise Stop(f"{region}/{component} existing record differs; no overwrite")
                elif status == 404 and not prior:
                    identity["registrations"][component] = "pending"
                    store.save(state)
                    method = "POST" if component == "is" else "PUT"
                    status, _ = client.request(target, component, method, body_for(target, component, identity))
                    if status not in (200, 201):
                        raise Stop(f"{region}/{component} write stopped with HTTP {status}; checkpoint retained")
                    status, remote = client.request(target, component)
                    errors = verify_remote(target, component, identity, remote) if status == 200 else ["read_failed"]
                    if errors:
                        report["registrations"].append({"region": region, "component": component,
                                                        "http_status": status, "mismatches": errors})
                        raise Stop(f"{region}/{component} exact readback failed; checkpoint retained")
                else:
                    raise Stop(f"{region}/{component} absence recheck failed; no write")
                identity["registrations"][component] = "verified"
                store.save(state)
                report["registrations"].append({"region": region, "application": target["application"],
                                                "device": target["device"], "component": component,
                                                "http_status": 200, "exact_match": True,
                                                "root_key_matches": True if component == "js" else None,
                                                "nonce_history_empty": True if component == "js" else None})
        report["passed"] = len(report["registrations"]) == 12
    except Stop as error:
        report["error"] = str(error)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--private-state", type=Path, default=DEFAULT_STATE)
    args = parser.parse_args()
    try:
        store = Store(args.private_state.absolute())
        keys = load_values()
        if any(not keys.get(target["key_name"]) for target in TARGETS):
            raise Stop("one or more required regional API keys are missing")
        with store.locked():
            result = execute(Client(keys), store, args.apply)
    except Stop as error:
        result = {"passed": False, "error": str(error)}
    except Exception:
        # Exceptions may quote private HTTP/JSON/checkpoint material.
        result = {"passed": False, "error": "executor stopped; private checkpoint retained; exception details withheld"}
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
