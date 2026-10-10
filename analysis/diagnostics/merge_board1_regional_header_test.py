#!/usr/bin/env python3
"""Local fixture-only tests: no TTN, hardware, or real private-header writes."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import shutil
import stat
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
HELPER = Path(__file__).with_name("merge_board1_regional_header.py")
assert HELPER.exists(), "missing guarded private-header merge implementation"
spec = importlib.util.spec_from_file_location("merge_header", HELPER)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

HEADER = ("#ifndef SECRETS_H\n#define SECRETS_H\n"
          '// Keep original whitespace and comments.\n'
          '#define LORAWAN_DEV_EUI "A000000000000001"\n'
          '#define LORAWAN_APP_EUI "0000000000000000"\n'
          '#define LORAWAN_APP_KEY "11111111111111111111111111111111"\n'
          '#define B2B_FLEET_KEY "55555555555555555555555555555555"\n'
          '#define CMD_BALLOON_ID 0x0001\n\n#endif\n').encode()


def fixture(base):
    root = base / "repo"
    (root / "firmware/include").mkdir(parents=True)
    (root / "firmware/src").mkdir()
    for relative in ("firmware/platformio.ini", "firmware/src/lorawan.cpp",
                     "firmware/include/config.h", "firmware/include/device_identity.h"):
        shutil.copyfile(ROOT / relative, root / relative)
    header = root / "firmware/include/secrets_board1.h"
    header.write_bytes(HEADER)
    header.chmod(0o600)
    (header.parent / "secrets.h").symlink_to(header.name)
    private = base / "private"
    private.mkdir(mode=0o700)
    checkpoint = private / "state.json"
    state = {"schema": m.SCHEMA, "targets": deepcopy(list(m.TARGETS)), "identities": {}}
    for index, region in enumerate(("EU", "AS", "AU"), 2):
        state["identities"][region] = {
            "allocation_started": True, "dev_eui": f"A00000000000000{index}",
            "app_key": str(index) * 32,
            "registrations": dict.fromkeys(("is", "js", "ns", "as"), "verified"),
        }
    checkpoint.write_text(json.dumps(state))
    checkpoint.chmod(0o600)
    checkpoint.with_suffix(".lock").touch(mode=0o600)
    return root, header, checkpoint, state


def refused(root, checkpoint, expected):
    try:
        m.merge(root, checkpoint, apply=True)
    except m.Stop as error:
        assert expected in str(error), str(error)
    else:
        raise AssertionError("unsafe input was accepted")


def main():
    with tempfile.TemporaryDirectory(prefix="board1-header-tests-") as directory:
        base = Path(directory)
        root, header, cp, state = fixture(base / "success")
        before_files = set(base.rglob("*"))
        report = m.merge(root, cp)
        assert report["passed"] and not report["header_changed"]
        assert report["mode"] == "dry_run" and report["new_macro_count"] == 6
        assert set(base.rglob("*")) == before_files, "dry run created a file"
        assert header.read_bytes() == HEADER
        assert report["preserved_US_join_fleet_command"]
        assert report["effective_regions_verified"] == ["US", "EU", "AS", "AU"]
        serialized = json.dumps(report)
        for identity in state["identities"].values():
            assert identity["dev_eui"] not in serialized and identity["app_key"] not in serialized

        result = m.merge(root, cp, apply=True)
        assert result["passed"] and result["header_changed"]
        merged = header.read_bytes()
        start = merged.index(b"// Board1 regional identities from verified private checkpoint.")
        assert merged[:start] + merged[merged.index(b"#endif", start):] == HEADER
        assert b'#define LORAWAN_DEV_EUI_EU "A000000000000002"' in merged
        assert b'#define LORAWAN_APP_KEY_AU "44444444444444444444444444444444"' in merged
        backup = Path(result["private_backup"])
        assert backup.read_bytes() == HEADER
        assert stat.S_IMODE(backup.stat().st_mode) == 0o600
        assert stat.S_IMODE(header.stat().st_mode) == 0o600
        assert (header.parent / "secrets.h").readlink() == Path("secrets_board1.h")
        assert json.loads(cp.read_text()) == state
        refused(root, cp, "regional macro")
        assert header.read_bytes() == merged and backup.read_bytes() == HEADER

        mutations = [
            ("schema", lambda s: s.update(schema="wrong")),
            ("targets", lambda s: s["targets"][0].update(device="stratolink-2-eu")),
            ("identities", lambda s: s["identities"].pop("AU")),
            ("verified", lambda s: s["identities"]["EU"]["registrations"].update(js="pending")),
            ("allocation", lambda s: s["identities"]["AS"].update(allocation_started=False)),
            ("hex", lambda s: s["identities"]["EU"].update(app_key="not-a-key")),
            ("hex", lambda s: s["identities"]["EU"].update(dev_eui="0" * 16)),
            ("distinct", lambda s: s["identities"]["AU"].update(dev_eui=s["identities"]["EU"]["dev_eui"])),
            ("distinct", lambda s: s["identities"]["AU"].update(app_key=s["identities"]["EU"]["app_key"])),
        ]
        for index, (expected, mutate) in enumerate(mutations):
            r, h, c, s = fixture(base / f"state-{index}")
            mutate(s)
            c.write_text(json.dumps(s))
            refused(r, c, expected)
            assert h.read_bytes() == HEADER
            assert not (c.parent / "secrets_board1.before-regions.h").exists()

        header_mutations = [
            ("regional macro", HEADER.replace(b"#endif", b'#define LORAWAN_DEV_EUI_EU ""\n#endif')),
            ("guard", HEADER.replace(b"#endif", b"#endif\n#define EXTRA 1")),
            ("JoinEUI", HEADER.replace(b"0000000000000000", b"0000000000000001")),
            ("command", HEADER.replace(b"0x0001", b"0x0002")),
            ("preprocessing", HEADER.replace(b"#endif", b'#error PRIVATE_SENTINEL\n#endif')),
        ]
        for index, (expected, changed) in enumerate(header_mutations):
            r, h, c, s = fixture(base / f"header-{index}")
            h.write_bytes(changed)
            refused(r, c, expected)
            assert h.read_bytes() == changed

        for index, kind in enumerate(("selector", "target_symlink", "mode", "checkpoint_symlink", "backup_conflict")):
            r, h, c, s = fixture(base / f"path-{index}")
            if kind == "selector":
                (h.parent / "secrets.h").unlink()
                (h.parent / "secrets.h").symlink_to("secrets_board2.h")
            elif kind == "target_symlink":
                real = h.with_name("other.h")
                h.rename(real)
                h.symlink_to(real.name)
            elif kind == "mode":
                h.chmod(0o644)
            elif kind == "checkpoint_symlink":
                real = c.with_name("other.json")
                c.rename(real)
                c.symlink_to(real.name)
            else:
                backup = c.parent / "secrets_board1.before-regions.h"
                backup.write_bytes(b"not original")
                backup.chmod(0o600)
            refused(r, c, {"selector": "selector", "target_symlink": "regular", "mode": "0600",
                           "checkpoint_symlink": "regular", "backup_conflict": "backup"}[kind])

        r, h, c, s = fixture(base / "race")
        original_effective = m.effective
        calls = 0
        def change_during_preflight(*args, **kwargs):
            nonlocal calls
            result = original_effective(*args, **kwargs)
            calls += 1
            if calls == 2:
                h.write_bytes(HEADER + b"// concurrent edit\n")
            return result
        with patch.object(m, "effective", side_effect=change_during_preflight):
            refused(r, c, "changed")
        assert h.read_bytes() == HEADER + b"// concurrent edit\n"

        # A snapshot taken after the private read must still describe those
        # exact bytes; otherwise a writer in that gap could be overwritten.
        r, h, c, s = fixture(base / "early-race")
        original_values = m.checkpoint_values
        def change_before_snapshot(data):
            values = original_values(data)
            h.write_bytes(HEADER.replace(b"Keep original", b"Concurrent editor"))
            return values
        with patch.object(m, "checkpoint_values", side_effect=change_before_snapshot):
            refused(r, c, "changed")
        assert b"Concurrent editor" in h.read_bytes()

        r, h, c, s = fixture(base / "early-checkpoint-race")
        def change_checkpoint_before_snapshot(data):
            values = original_values(data)
            changed = deepcopy(s)
            changed["identities"]["EU"]["app_key"] = "6" * 32
            c.write_text(json.dumps(changed))
            return values
        with patch.object(m, "checkpoint_values", side_effect=change_checkpoint_before_snapshot):
            refused(r, c, "changed")
        assert h.read_bytes() == HEADER
    print("PASS: dry-run is read-only; six-field merge preserves identities; private backup, conflict, malformed-state, selector, permissions, preprocessing and TOCTOU guards")


if __name__ == "__main__":
    main()
