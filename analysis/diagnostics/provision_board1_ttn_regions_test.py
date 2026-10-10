#!/usr/bin/env python3
"""Pure fake-transport tests: never contacts TTN or accesses a firmware header."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import stat
import tempfile

from provision_board1_ttn_regions import (
    COMPONENTS, SCHEMA, TARGETS, Stop, Store, body_for, endpoint, execute, mismatches,
)


class FakeClient:
    def __init__(self):
        self.calls = []
        self.records = {}
        self.allocations = 0
        self.read_status = {}
        self.fail_write = None
        self.fail_allocation = False
        self.race_on_read = None

    @property
    def writes(self):
        return [call for call in self.calls if call[2] != "GET"]

    def request(self, target, component, method="GET", body=None, allocate=False):
        assert target in TARGETS and component in COMPONENTS
        key = (target["region"], component)
        self.calls.append((target["region"], component, method, allocate))
        assert target["device"] != "stratolink-1"
        if allocate:
            self.allocations += 1
            if self.fail_allocation:
                return 0, {}
            return 200, {"dev_eui": f"{self.allocations:016X}"}
        if method == "GET":
            if self.race_on_read == len(self.calls):
                self.records[key] = {"ids": {"device_id": "unexpected"}}
            if key in self.read_status:
                return self.read_status[key], {}
            return (200, deepcopy(self.records[key])) if key in self.records else (404, {})
        assert method == ("POST" if component == "is" else "PUT")
        assert key not in self.records, "executor attempted to overwrite an existing registration"
        if self.fail_write == (key, "not-stored"):
            return 0, {}
        self.records[key] = deepcopy(body["end_device"])
        if self.fail_write == (key, "stored"):
            return 0, {}
        return 200, deepcopy(self.records[key])


def main():
    assert {t["device"] for t in TARGETS} == {
        "stratolink-1-eu", "stratolink-1-as", "stratolink-1-au"}
    assert endpoint(TARGETS[2], "is")[0] == "eu1.cloud.thethings.network"
    assert endpoint(TARGETS[2], "ns")[0] == "nam1.cloud.thethings.network"
    identity = {"dev_eui": "01" * 8, "app_key": "02" * 16}
    for target in TARGETS:
        ns = body_for(target, "ns", identity)
        settings = ns["end_device"]["mac_settings"]
        assert settings["rx2_frequency"] == str(target["rx2_hz"])
        assert settings["desired_rx2_frequency"] == str(target["rx2_hz"])
        assert settings["rx2_data_rate_index"] == target["rx2_dr"]
        assert settings["desired_rx2_data_rate_index"] == target["rx2_dr"]
        assert settings["status_count_periodicity"] == 0
        assert settings["status_time_periodicity"] == "0s"
        assert settings["schedule_downlinks"] is True
        assert settings["use_adr"] is False
        for component in COMPONENTS:
            body = body_for(target, component, identity)
            assert not any(name in body["end_device"] for name in (
                "session", "pending_session", "mac_state", "pending_mac_state", "used_dev_nonces"))

    # Missing non-wrapper false protobuf fields are equivalent to false;
    # missing wrapper settings must never be silently accepted as defaults.
    assert not mismatches({"supports_class_b": False}, {})
    assert mismatches({"mac_settings": {"use_adr": False}}, {})
    assert mismatches({"skip_payload_crypto_override": False}, {})
    assert not mismatches({"mac_settings": {"rx1_delay": 5, "rx2_data_rate_index": 3}},
                          {"mac_settings": {"rx1_delay": "RX_DELAY_5", "rx2_data_rate_index": "DATA_RATE_3"}})
    assert mismatches({"mac_settings": {"rx1_delay": 5}}, {"mac_settings": {"rx1_delay": True}})

    with tempfile.TemporaryDirectory(prefix="board1-regional-tests-") as directory:
        root = Path(directory)

        def new_store(name):
            return Store(root / name / "state.json")

        checked = FakeClient()
        checked_store = new_store("check")
        report = execute(checked, checked_store)
        assert report["passed"] and len(report["preflight"]) == 12
        assert not checked.writes and not checked_store.path.exists()

        for name, setup in (
            ("existing", lambda client: client.records.update({("AU", "as"): {"ids": {"device_id": "other"}}})),
            ("unreadable", lambda client: client.read_status.update({("EU", "js"): 403})),
        ):
            client = FakeClient()
            setup(client)
            store = new_store(name)
            result = execute(client, store, True)
            assert not result["passed"] and len(client.calls) == 12
            assert not client.writes and not store.path.exists()

        client = FakeClient()
        store = new_store("happy")
        report = execute(client, store, True)
        assert report["passed"] and len(report["registrations"]) == 12
        assert len(client.writes) == 15 and client.allocations == 3
        assert all(call[2] == "GET" for call in client.calls[:12])
        assert report["header_changed"] is False and report["us_device_accessed"] is False
        private = store.load()
        assert private["schema"] == SCHEMA
        assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
        assert stat.S_IMODE(store.path.parent.stat().st_mode) == 0o700
        assert len({i["app_key"] for i in private["identities"].values()}) == 3
        assert len({i["dev_eui"] for i in private["identities"].values()}) == 3
        for item in private["identities"].values():
            assert item["app_key"] not in json.dumps(report)
            assert item["dev_eui"] not in json.dumps(report)
            assert set(item["registrations"].values()) == {"verified"}
        writes_before = len(client.writes)
        assert execute(client, store, True)["passed"]
        assert len(client.writes) == writes_before

        # Existing-state comparisons protect each component's configured data.
        changed = deepcopy(client.records[("AS", "ns")])
        client.records[("AS", "ns")]["mac_settings"]["rx2_data_rate_index"] = 3
        assert not execute(client, store, True)["passed"]
        assert len(client.writes) == writes_before
        client.records[("AS", "ns")] = changed
        client.records[("AS", "js")]["root_keys"]["app_key"]["key"] = "03" * 16
        mismatch_report = execute(client, store, True)
        assert not mismatch_report["passed"] and len(client.writes) == writes_before
        assert "03" * 16 not in json.dumps(mismatch_report)

        for mode in ("stored", "not-stored"):
            client = FakeClient()
            store = new_store(f"uncertain-{mode}")
            client.fail_write = (("EU", "js"), mode)
            result = execute(client, store, True)
            assert not result["passed"]
            before = store.load()
            assert before["identities"]["EU"]["registrations"]["js"] == "pending"
            writes_before = len(client.writes)
            client.fail_write = None
            resumed = execute(client, store, True)
            if mode == "stored":
                assert resumed["passed"]
                assert store.load()["identities"]["EU"]["app_key"] == before["identities"]["EU"]["app_key"]
            else:
                assert not resumed["passed"] and len(client.writes) == writes_before
                assert client.allocations == 1

        client = FakeClient()
        client.fail_allocation = True
        store = new_store("uncertain-allocation")
        assert not execute(client, store, True)["passed"]
        assert store.load()["identities"]["EU"]["allocation_started"] is True
        assert not execute(client, store, True)["passed"]
        assert client.allocations == 1
        assert not any(not call[3] for call in client.writes)

        # A new record appearing after the batch gate blocks the per-write gate.
        client = FakeClient()
        client.race_on_read = 14  # 12 preflight reads, allocation, then IS read.
        store = new_store("race")
        assert not execute(client, store, True)["passed"]
        assert len(client.writes) == 1 and client.writes[0][3]
        assert store.load()["identities"]["EU"]["dev_eui"]

        # Used nonce history prevents resuming a device that has gone active.
        client = FakeClient()
        store = new_store("nonce-history")
        assert execute(client, store, True)["passed"]
        writes_before = len(client.writes)
        client.records[("AU", "js")]["used_dev_nonces"] = [0]
        assert not execute(client, store, True)["passed"]
        assert len(client.writes) == writes_before

        # No state fallback/reset when the private checkpoint is wrong.
        private = store.load()
        private["targets"][0]["device"] = "stratolink-2-eu"
        store.save(private)
        try:
            store.load()
        except Stop:
            pass
        else:
            raise AssertionError("target mismatch accepted")

        lock_store = new_store("lock")
        with lock_store.locked():
            try:
                with lock_store.locked():
                    raise AssertionError("concurrent executor accepted")
            except Stop:
                pass

    print("PASS: fixed Board1 regional targets, twelve-read gate, exact resume, "
          "no overwrite/delete, durable private keys, ambiguity stops, and no hardware/header access")


if __name__ == "__main__":
    main()
