"""Exercise the worker's real orchestration without NOAA, credentials, or GRIB."""
import ast
import contextlib
import io
from pathlib import Path
import types
import unittest


class IngestFailureTests(unittest.TestCase):
    def worker(self, build_cube, devices):
        tree = ast.parse(Path(__file__).with_name("gfs_ingest.py").read_text())
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


if __name__ == "__main__":
    unittest.main()
