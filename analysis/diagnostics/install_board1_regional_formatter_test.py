#!/usr/bin/env python3
"""Pure transport fixtures; no real TTN, header, or hardware mutations."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile

PATH = Path(__file__).with_name("install_board1_regional_formatter.py")
assert PATH.exists(), "missing guarded regional formatter implementation"
spec = importlib.util.spec_from_file_location("regional_formatter", PATH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class Client:
    def __init__(self, identities):
        self.records = {}
        self.js = {}
        self.puts = []
        self.fail = None
        for target in m.TARGETS:
            region = target["region"]
            self.records[region] = m.body_for(target, "as", identities[region])["end_device"]
            self.records[region]["formatters"] = {"down_formatter": "FORMATTER_NONE"}
            self.js[region] = m.body_for(target, "js", identities[region])["end_device"]

    def read_as(self, target):
        return 200, deepcopy(self.records[target["region"]])

    def read_js(self, target):
        return 200, deepcopy(self.js[target["region"]])

    def put_as(self, target, body):
        assert body["field_mask"]["paths"] == ["formatters.up_formatter", "formatters.up_formatter_parameter"]
        assert set(body["end_device"]) == {"ids", "formatters"}
        assert set(body["end_device"]["formatters"]) == {"up_formatter", "up_formatter_parameter"}
        region = target["region"]
        self.puts.append(region)
        self.records[region]["formatters"].update(body["end_device"]["formatters"])
        return (0, {}) if self.fail == region else (200, {})


def main():
    source = m.SOURCE.read_text()
    identities = {r: {"dev_eui": f"A00000000000000{i}", "app_key": str(i) * 32}
                  for i, r in enumerate(("EU", "AS", "AU"), 2)}
    with tempfile.TemporaryDirectory() as directory:
        private = Path(directory)
        client = Client(identities)
        store = m.Store(private / "state.json")
        report = m.execute(client, store, identities, source, False)
        assert report["passed"] and not store.path.exists() and not client.puts
        report = m.execute(client, store, identities, source, True)
        assert report["passed"] and client.puts == ["EU", "AS", "AU"]
        assert all(row["unrelated_fields_unchanged"] for row in report["regions"])
        saved = json.loads(store.path.read_text())
        assert saved["regions"]["EU"]["before"]["formatters"] == {"down_formatter": "FORMATTER_NONE"}
        assert m.execute(client, store, identities, source, True)["passed"]
        assert client.puts == ["EU", "AS", "AU"]
        assert all(i["dev_eui"] not in json.dumps(report) for i in identities.values())

        for bad in ("override", "identity", "root_key", "source"):
            c = Client(identities)
            if bad == "override":
                c.records["AU"]["formatters"]["up_formatter"] = "FORMATTER_CAYENNELPP"
            elif bad == "identity":
                c.records["AU"]["ids"]["dev_eui"] = "0" * 16
            elif bad == "root_key":
                c.js["AU"]["root_keys"]["app_key"]["key"] = "F" * 32
            result = m.execute(c, m.Store(private / f"{bad}.json"), identities,
                               source + "bad" if bad == "source" else source, True)
            assert not result["passed"] and not c.puts

        c = Client(identities)
        c.fail = "EU"
        uncertain = m.Store(private / "uncertain.json")
        result = m.execute(c, uncertain, identities, source, True)
        assert not result["passed"] and c.puts == ["EU"]
        assert json.loads(uncertain.path.read_text())["regions"]["EU"]["phase"] == "pending"
        c.fail = None
        assert m.execute(c, uncertain, identities, source, True)["passed"]
        assert c.puts == ["EU", "AS", "AU"]

        c = Client(identities)
        c.fail = "EU"
        absent = m.Store(private / "ambiguous-not-stored.json")
        m.execute(c, absent, identities, source, True)
        c.records["EU"]["formatters"] = {"down_formatter": "FORMATTER_NONE"}
        c.fail = None
        assert not m.execute(c, absent, identities, source, True)["passed"]
        assert c.puts == ["EU"]
    print("PASS: exact formatter source; three-device preflight; two-field writes; retained private snapshots; no retry after ambiguous absence; exact resume and unrelated-field preservation")


if __name__ == "__main__":
    main()
