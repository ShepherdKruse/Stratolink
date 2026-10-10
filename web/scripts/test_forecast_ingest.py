"""Exercise the worker's real orchestration without NOAA, credentials, or GRIB."""
import ast
import contextlib
import io
import os
from pathlib import Path
import re
import types
import unittest

INGEST = Path(__file__).with_name("gfs_ingest.py")


def extract(names):
    """Load just the named top-level functions / constants of gfs_ingest.py (it
    imports pygrib + numpy at module level, which the test runner lacks)."""
    tree = ast.parse(INGEST.read_text())
    body = [
        node for node in tree.body
        if (isinstance(node, ast.FunctionDef) and node.name in names)
        or (isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id in names for t in node.targets))
    ]
    namespace = {"os": os}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(INGEST), "exec"), namespace)
    return namespace


class IngestFailureTests(unittest.TestCase):
    def worker(self, build_cube, devices):
        tree = ast.parse(INGEST.read_text())
        main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
        module = ast.Module(body=[main], type_ignores=[])
        namespace = {
            "sys": types.SimpleNamespace(argv=["gfs_ingest.py"]),
            "active_devices": lambda: devices,
            "latest_cycle": lambda: types.SimpleNamespace(isoformat=lambda: "test-cycle"),
            "mission_track": lambda *_: [{"lat": 0, "lon": 0}],
            "float_pressure": lambda _: 250,
            "build_cube": build_cube,
        }
        exec(compile(module, str(Path(__file__)), "exec"), namespace)
        return namespace["main"]

    def test_ingest_error_fails_job_after_processing_other_devices(self):
        attempted = []

        def build(device, *_):
            attempted.append(device)
            if device == "one":
                raise RuntimeError("simulated NOAA outage")

        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            self.worker(build, [("one", None), ("two", None)])()
        self.assertEqual(attempted, ["one", "two"])

    def test_empty_fleet_does_not_download_weather(self):
        def build(*_):
            self.fail("No weather work expected")
        with contextlib.redirect_stdout(io.StringIO()):
            self.worker(build, [])()


class ReconTubeGeometryTests(unittest.TestCase):
    """The per-slice geometry of the reconstruction tube (pure helpers)."""

    @classmethod
    def setUpClass(cls):
        cls.g = extract({
            "RECON_HALF_BASE_DEG", "RECON_HALF_PER_H", "RECON_HALF_MIN_DEG", "RECON_HALF_MAX_DEG",
            "recon_half_deg", "gap_hours_at", "unwrap_lons",
        })

    def test_half_width_grows_with_gap_length_within_clamps(self):
        half = self.g["recon_half_deg"]
        self.assertEqual(half(0), 9)                 # floor: short gaps
        self.assertEqual(half(60), 9)                # 6 + 3 = the floor exactly
        self.assertAlmostEqual(half(100), 11)
        self.assertAlmostEqual(half(200), 16)
        self.assertEqual(half(280), 20)              # cap
        self.assertEqual(half(10_000), 20)

    def test_gap_hours_at_uses_the_longest_gap_a_slice_can_be_read_by(self):
        h = 3_600_000
        fixes = [(0, 0, 0), (10 * h, 0, 0), (12 * h, 0, 0), (50 * h, 0, 0)]   # gaps 10 h, 2 h, 38 h
        gap_at = self.g["gap_hours_at"]
        self.assertEqual(gap_at(fixes, 5 * h, 3 * h), 10)
        # A slice within one step of the next gap's start is read by that gap too.
        self.assertEqual(gap_at(fixes, 11 * h, 3 * h), 38)
        self.assertEqual(gap_at(fixes, 30 * h, 3 * h), 38)
        self.assertEqual(gap_at(fixes, 52 * h, 3 * h), 38)   # trailing slice still touches the last gap
        self.assertEqual(gap_at(fixes, -5 * h, 3 * h), 0)    # lead-in slice: no bridge reads it
        self.assertEqual(gap_at(fixes, 60 * h, 3 * h), 0)

    def test_unwrap_lons_is_continuous_and_anchored_at_the_last_fix(self):
        unwrap = self.g["unwrap_lons"]
        self.assertEqual(unwrap([]), [])
        self.assertEqual(unwrap([-122.4, -100.0, -4.5]), [-122.4, -100.0, -4.5])
        # Eastward across the dateline: no +360 jump, last value kept raw.
        self.assertEqual(unwrap([170.0, 178.0, -178.0, -170.0]), [-190.0, -182.0, -178.0, -170.0])


class DeviceAliasMirrorTests(unittest.TestCase):
    """The ingest must query the same canonical + alias telemetry ids as the
    compute (lib/devices/aliases.ts), or the tube is built from a partial track."""

    @classmethod
    def setUpClass(cls):
        cls.g = extract({"DEVICE_ID_ALIASES", "telemetry_device_ids", "device_id_filter"})

    def test_alias_map_matches_the_typescript_source(self):
        ts = (INGEST.parent.parent / "lib" / "devices" / "aliases.ts").read_text()
        block = re.search(r"DEVICE_ID_ALIASES[^{]*\{(.*?)\};", ts, re.S).group(1)
        ts_map = dict(re.findall(r"['\"]([^'\"]+)['\"]\s*:\s*['\"]([^'\"]+)['\"]", block))
        self.assertTrue(ts_map, "could not parse DEVICE_ID_ALIASES from aliases.ts")
        self.assertEqual(self.g["DEVICE_ID_ALIASES"], ts_map)

    def test_telemetry_ids_expand_canonical_and_alias(self):
        ids = self.g["telemetry_device_ids"]
        self.assertEqual(ids("stratolink-3"), ["stratolink-3", "stratolink-3-eu"])
        self.assertEqual(ids("stratolink-3-eu"), ["stratolink-3", "stratolink-3-eu"])
        self.assertEqual(ids("stratolink-2"), ["stratolink-2"])
        self.assertEqual(self.g["device_id_filter"]("stratolink-3"), "in.(stratolink-3,stratolink-3-eu)")


if __name__ == "__main__":
    unittest.main()
